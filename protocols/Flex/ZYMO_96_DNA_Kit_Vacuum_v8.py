"""
ZymoBIOMICS 96 DNA Kit. 

Prefiltered with Pall Corporation AcroPrep Advance 96 Well 1 mL Short Tip Natural PP
Sub in Pall Corporation AcroPrep Advance 96 Filter Plate for ZR-Spin Plate. Increases tip length to prevent contamination. 

Utilizing Opentrons Vacuum Manifold. 

""" 


from opentrons import protocol_api, types

metadata = {
    "protocolName": "ZymoBIOMICS 96 DNA Kit - Vacuum Module",
    "author": "Tavis Goldwire",
    "description": "Spin-plate DNA extraction on the vacuum manifold, 8-96 samples, with pre filtering.",
}


requirements = {"robotType": "Flex", "apiLevel": "2.30"} # i think this can be 2.31 now. check


# Labware
CUSTOM = {"namespace": "custom_beta", "version": 3} # need to build custom labware for prefilter plate and new spin plate. 
RESERVOIR = "nest_12_reservoir_22ml"   
# RESERVOIR_MAX = 15_000      # uL per reservoir well
# WELL_MARGIN = 1_500         # uL left in each reservoir well after its last draw. Estimate, NOT validated:
#                             # the well's V-bottom holds ~0.7 mL below 2 mm
TIPRACK = "opentrons_flex_96_tiprack_1000ul"
ELUTION_TIPRACK = "opentrons_flex_96_tiprack_50ul"



# Parameters

def add_parameters(p: protocol_api.ParameterContext):
    p.add_str(
        variable_name="run_mode",
        display_name="Run Mode",
        description="Dry runs skip delays and return tips to the rack.",
        default="real",
        choices=[
            {"display_name": "Real run", "value": "real"},
            {"display_name": "Dry run - 5 s vacuums", "value": "dry_short"},
            {"display_name": "Dry run - full vacuums", "value": "dry_full"},
        ],
    )
    p.add_int(
        variable_name="sample_columns",
        display_name="Sample Columns",
        description="Tips, samples and reagent wells in columns 1 to this number. 6 = 48 samples.",
        default=6,
        minimum=1,
        maximum=12,
    )
    p.add_bool(
        variable_name="blot",
        display_name="Blot Spin Plate",
        description="Touch the plate underside to the B4 towel before elution.",
        default=True,
    )
    p.add_float(
        variable_name="elution_volume",
        display_name="Elution Volume",
        description="Water per well, delivered with 50 uL tips.",
        default=50.0,
        minimum=20.0,
        maximum=50.0,
        unit="uL",
    )
    p.add_int(
        variable_name="elution_incubation",
        display_name="Elution Incubation",
        description="Soak on the membrane before the elution vacuum.",
        default=60,
        minimum=0,
        maximum=600,
        unit="s",
    )
    p.add_int(
        variable_name="load_pressure",
        display_name="Load Vacuum Pressure",
        description="Vacuum held while lysate is dispensed into the spin plate.",
        default=-600,
        minimum=-800,
        maximum=-50,
        unit="mbar",
    )



# Run Loop

def run(ctx: protocol_api.ProtocolContext):
    
    p = ctx.params
    dry = p.run_mode != "real" # Dry Run 


    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    spin_plate = collar.load_labware("cytiva_96_wellplate_1000ul_shorttip_filter", "AcroPrep Spin Plate", **CUSTOM) 
    spacer = ctx.load_adapter("custom_vacuum_manifold_spacer_tall", "D2", **CUSTOM)  # this needs to be updated with new spacers
    elution_plate = spacer.load_labware("elution_plate_placeholder", "Elution plate", **CUSTOM) 
    samples = ctx.load_labware("nest_96_wellplate_2ml_deep", "A2", "Samples")["A1"] # collection plate. post filtered. 

    tip_adapters = {s: ctx.load_adapter("opentrons_flex_96_tiprack_adapter", s) for s in ("A1", "B1", "D1")}
    racks = [adapter.load_labware("opentrons_flex_96_tiprack_1000ul") for adapter in tip_adapters.values()]
    elution_tips = ctx.load_labware("opentrons_flex_96_tiprack_50ul", "C4", "50 uL tips for elution") 
    # pad = ctx.load_labware("dutton_blot_pad", "B4", "Blot towel", **CUSTOM) if p.blot else None       Wasnt necessary for short tip so queued to delete 

    pip = ctx.load_instrument("flex_96channel_1000", "left", tip_racks=racks)  # full pickup: A1 = whole plate

    n = p.sample_columns # How many Columns are being done

    if n < 12: #parital or full run. might not need this
        full = True
    else:
        full = False


    def trough(slot, name, color, per_tip_ul): #load troughs
        reservoir = ctx.load_labware(RESERVOIR, slot, name)
        fill = 8 * per_tip_ul + 1000 # 8 pipettes * how much needed + dead space
        liquid = ctx.define_liquid(name, "ZymoBIOMICS", color)
        for well in reservoir.wells()[:n]:
            well.load_liquid(liquid, fill)
        ctx.comment(f"Setup: {slot} {name}: {fill / 1000:.1f} mL in each of wells A1-A{n}")
        return reservoir["A1"]   # full pickup: aspirating at A1 puts tip column k in well k


    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 1200) # 1200 uL of Binding Buffer
    wash1 = trough("B3", "DNA Wash Buffer 1", "#FFFB00", 400) # 400 uL of Wash 1
    wash2 = trough("C2", "DNA Wash Buffer 2", "#00FF6E", 900) # 700 and 200 uL of Wash 2
    water = trough("C3", "Nuclease-free water", "#0048FF", p.elution_volume) # Depends on how much elution is requested
    lysate = ctx.define_liquid("Clarified lysate", "Operator-loaded", "#B266FF") # What is this doing??

    set_rates("lysate")
    for i in range(LOADS):
        task = pump_on()
        pip.aspirate(load_vol, samples.bottom(ASP_Z))
        pip.move_to(samples.top(), speed=EXIT_SPEED)   # slow exit, less drip
        pip.air_gap(AIR_GAP)
        pip.dispense(load_vol + AIR_GAP, spin_plate["A1"].bottom(LOAD_Z))
        pip.blow_out(spin_plate["A1"].top(TOP_Z))
        park()
        pump_off(task)
        pull(p.final_load_time if i == LOADS - 1 else p.load_time)
    discard_tip()







# Step 1: Transfer Samples to Pre-Filter (Robot Prep) and spin down


# Lift up collar and put on side next to vacuum. 
# Put collection plate back in its spot (or trash collection plate and but this new one there.)
# Put Back collar. and Put AcroPrep Spin Plate on Top.

# Step 2: Transfer 1,200 uL of Binding Buffer to Sample

# pick up tips, aspirate 600 uL of buffer. dispesne into sample. 
# aspirate another 600uL of buffer and dispense into sample. Mix for 2 minutes. 


# Step 3: Transfers Sample Buffer mix (1600 uL) to AcroPrep Spin Plate ( In 2-4 phases )

# aspirate samples, dispense in spin plate
# Turn on vacuum ~5 min. 
# repeat 2 more times. This is to ensure no build up in the wells of salt residue. 
# pull through all flowthrough no collection
# liquid check to make sure it vacuumed the whole thing, if not vacuum again. check again, if still liquid pause and alert
#Trash tips


# Step 4: Add DNA Wash Buffer 1 (400 uL) to Spin Plate

# Pick up new tips. Aspirate 400 uL of buffer. Dispense to spin plate.
# Pause 30 seconds (is this necessary?)
# Vacuum At least 5 min
# liquid check , repeat if needed
# Trash tips

# Step 5: Two Phases of Wash Buffer 2 (700 uL + 200 uL) to Spin Plate 

# Pick up new tips. Aspirate 700 uL of wash buffer 2. 
# Pause briefly (? same as above)
# Vacuum for at least 5 min. 
# Aspirate 200 uL, dispense in spin plate. 
# vacuum for at least 5 min 
# liquid check + supplemental vacuuming. This is the drying step before elution. 
# Trash tips

# Step 6: Elution Transfer and Recovery 

# Pick up new tips (50 uL) and aspirate 20 - 50 of preheated elution buffer ( add temp on somewhere earlier in the script)
# Dispense slowly to the top of the matrix (this needs to be highly accurate)
# Incubate for at least 1 minute. 
# Pull through 


# Step 7: HRC Plate Preparation 

# Once rest of protocol is validated add this step. Not priority rn  
# Need to pierce foil / transfer samples into it. 
# Likely spin down manually. 
