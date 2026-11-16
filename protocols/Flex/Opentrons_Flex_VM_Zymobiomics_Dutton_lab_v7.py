"""
ZymoBIOMICS 96 DNA Kit on the Opentrons Flex + Vacuum Module (Dutton lab v7).

Before the run (manual): prefilter the lysate through the AcroPrep prefilter plate and put
the clarified lysate in a 2 mL deep-well plate in A2.

Deck
  A1 B1 D1  1000 uL tip racks on 96 adapters      C4  50 uL tip rack (elution)
  A2        clarified lysate (deep-well plate)    A3  vacuum module + tall collar + AcroPrep spin plate
  B2 B3     Binding Buffer, Wash Buffer 1         D2  7.25 mm spacer + NEST PCR plate (elution)
  C2        Wash Buffer 2                         C1  temperature module + flat adapter + water
  D3        waste chute
  Reagents are in 12-well reservoirs: with full pickup at A1, tip column k draws from well k.

Partial plates (Sample Columns < 12): tip racks hold tips in columns 1-N only, samples go in
columns 1-N, and only reservoir wells 1-N are filled. Seal spin-plate columns N+1 to 12.

Ends at elution. HRC inhibitor removal (kit step 14) is done off-deck.
"""

from opentrons import protocol_api

metadata = {
    "protocolName": "ZymoBIOMICS 96 DNA Kit - Flex + Vacuum Module (Dutton lab v7)",
    "author": "Tavis Goldwire",
    "description": "Spin-plate DNA extraction on the vacuum manifold, 8-96 samples, through elution.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.31"}

# Labware
CUSTOM = {"namespace": "custom_beta", "version": 1}
SPIN_PLATE = "cytiva_96_wellplate_1000ul_shorttip_filter"
SPACER = "custom_vacuum_manifold_spacer_7_25mm"
ELUTION_PLATE = "nest_96_wellplate_100ul_pcr_full_skirt"
SAMPLE_PLATE = "nest_96_wellplate_2ml_deep"
RESERVOIR = "nest_12_reservoir_22ml"
RESERVOIR_MAX = 15_000      # uL per reservoir well
WELL_MARGIN = 1_500         # uL left in each reservoir well after its last draw

# Volumes, uL per well
BINDING_VOL = 600           # added twice
LOADS = 4                   # lysate + binding buffer goes onto the spin plate in this many loads
WASH1_VOL = 400
WASH2_VOLS = (700, 200)
MIX_VOL = 900
MIX_REPS = 10
AIR_GAP = 20

# Flow rates, uL/s: (aspirate, dispense)
RATES = {
    "binding": (80, 150),
    "mix": (150, 150),
    "lysate": (100, 15),
    "wash": (150, 180),
    "water": (6, 10),
}

# Heights, mm. Spin plate heights are above the membrane (the definition's well bottom).
ASP_Z = 0.75                # above well bottom, every aspiration
MIX_DISP_Z = 5              # above the sample well bottom
TOP_Z = -5                  # below well top: washes and blow-outs
PARK_Z = 5                  # above the sample plate, where tips wait during a pull
EXIT_SPEED = 5              # mm/s, leaving the sample well after each load draw
LOAD_Z = 3                  # above the membrane, lysate dispense. NOT tested on this plate
ELUTION_Z = 2               # above the membrane, water dispense. NOT tested on this plate

# Vacuum (pump power, no pressure setpoint)
PUMP_POWER = 100            # %
LOAD_TIME = 300             # s, after loads 1-3
FINAL_LOAD_TIME = 600       # s, after the last load
WASH_TIME = 540             # s, after each wash
DRY_TIME = 600              # s, extra pull to dry the membrane
ELUTION_POWERS = (50, 75, 100)  # %, stepped up over ELUTION_TIME
ELUTION_TIME = 240          # s, total
ELUTION_SOAK = 300          # s, water on the membrane before the elution pull
DRY_RUN_PULL = 5            # s, every pull in a dry run

# Gripper
SPACER_GRIP_RAISE = 5       # mm above default grip, clears the manifold rim
MODULE_DROP_X = -1.0        # drops on the vacuum module land ~1 mm right


def add_parameters(p: protocol_api.ParameterContext):
    p.add_bool(
        variable_name="dry_run",
        display_name="Dry Run",
        description="5 s vacuums, no delays, tips returned to the rack.",
        default=False,
    )
    p.add_int(
        variable_name="sample_columns",
        display_name="Sample Columns",
        description="Tips, samples and reagent wells in columns 1 to this number. 6 = 48 samples.",
        default=6,
        minimum=1,
        maximum=12,
    )
    p.add_int(
        variable_name="lysate_volume",
        display_name="Lysate Volume",
        description="Clarified lysate per sample well. Kit: up to 400 uL.",
        default=400,
        minimum=100,
        maximum=400,
        unit="uL",
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
        variable_name="elution_temp",
        display_name="Elution Water Temp",
        description="C1 module heats the water from the start of Wash 2. 0 = no heating.",
        default=65,
        minimum=0,
        maximum=70,
        unit="C",
    )


def run(ctx: protocol_api.ProtocolContext):
    p = ctx.params
    dry = p.dry_run
    n = p.sample_columns

    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    spin_plate = collar.load_labware(SPIN_PLATE, "AcroPrep spin plate", **CUSTOM)
    spacer = ctx.load_adapter(SPACER, "D2", **CUSTOM)
    elution_plate = spacer.load_labware(ELUTION_PLATE, "Elution plate")
    samples = ctx.load_labware(SAMPLE_PLATE, "A2", "Clarified lysate")
    temp_mod = ctx.load_module("temperatureModuleV2", "C1")
    water_adapter = temp_mod.load_adapter("opentrons_universal_flat_adapter")

    tip_adapters = {s: ctx.load_adapter("opentrons_flex_96_tiprack_adapter", s) for s in ("A1", "B1", "D1")}
    racks = [a.load_labware("opentrons_flex_96_tiprack_1000ul") for a in tip_adapters.values()]
    elution_tips = ctx.load_labware("opentrons_flex_96_tiprack_50ul", "C4", "50 uL tips")
    pip = ctx.load_instrument("flex_96channel_1000", "left", tip_racks=racks)

    # ---------------- Liquids ----------------
    def trough(slot, name, color, per_tip_ul, on=None):
        """Fill wells 1-n of a 12-well reservoir with what each tip column draws, plus margin."""
        reservoir = on.load_labware(RESERVOIR, name) if on else ctx.load_labware(RESERVOIR, slot, name)
        fill = 8 * per_tip_ul + WELL_MARGIN
        if fill > RESERVOIR_MAX:
            raise ValueError(f"{name} needs {fill} uL per well; the reservoir holds {RESERVOIR_MAX}.")
        liquid = ctx.define_liquid(name, "ZymoBIOMICS", color)
        for well in reservoir.wells()[:n]:
            well.load_liquid(liquid, fill)
        return reservoir["A1"]

    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 2 * BINDING_VOL)
    wash1 = trough("B3", "DNA Wash Buffer 1", "#FFFB00", WASH1_VOL)
    wash2 = trough("C2", "DNA Wash Buffer 2", "#00FF6E", sum(WASH2_VOLS))
    water = trough("C1", "Nuclease-free water", "#0048FF", p.elution_volume, on=water_adapter)

    lysate = ctx.define_liquid("Clarified lysate", "Prefiltered by hand", "#B266FF")
    for column in samples.columns()[:n]:
        for well in column:
            well.load_liquid(lysate, p.lysate_volume)

    sample = samples["A1"]
    spin = spin_plate["A1"]
    load_vol = (p.lysate_volume + 2 * BINDING_VOL) / LOADS

    # ---------------- Helpers ----------------
    def hold(seconds):
        if not dry:
            ctx.delay(seconds=seconds)

    def pull(seconds, power=PUMP_POWER, vent=True):
        """Run the pump for `seconds`, then vent."""
        if dry:
            seconds = DRY_RUN_PULL
        vm.close_vent()
        task = vm.start_set_vacuum_power(power, seconds, vent_after=vent, equalize_timeout_s=20)
        ctx.wait_for_tasks([task])

    def set_rates(name):
        pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES[name]

    def discard_tip():
        if dry:
            pip.return_tip()
        else:
            pip.drop_tip(chute)

    def wash(volume, source):
        pip.aspirate(volume, source.bottom(ASP_Z))
        pip.air_gap(AIR_GAP)
        pip.dispense(volume + AIR_GAP, spin.top(TOP_Z))
        pip.blow_out(spin.top(TOP_Z))

    # ---------------- 1. Binding buffer + mix ----------------
    # push_out=0 until the final blow-out, so the tips stay in the well between mixes.
    pip.pick_up_tip()
    set_rates("binding")
    for _ in range(2):
        pip.aspirate(BINDING_VOL, binding.bottom(ASP_Z))
        pip.air_gap(AIR_GAP)
        pip.dispense(BINDING_VOL + AIR_GAP, sample.top(TOP_Z), push_out=0)

    set_rates("mix")
    for _ in range(MIX_REPS):
        pip.aspirate(MIX_VOL, sample.bottom(ASP_Z))
        pip.dispense(MIX_VOL, sample.bottom(MIX_DISP_Z), push_out=0)
    pip.blow_out(sample.top(TOP_Z))

    # ---------------- 2. Load spin plate, pump on while dispensing ----------------
    set_rates("lysate")
    for i in range(LOADS):
        vm.close_vent()
        pump = vm.start_set_vacuum_power(PUMP_POWER)
        pip.aspirate(load_vol, sample.bottom(ASP_Z))
        pip.move_to(sample.top(), speed=EXIT_SPEED)
        pip.air_gap(AIR_GAP)
        pip.dispense(load_vol + AIR_GAP, spin.bottom(LOAD_Z))
        pip.blow_out(spin.top(TOP_Z))
        pip.move_to(sample.top(PARK_Z))
        vm.stop_vacuum_pump()
        ctx.wait_for_tasks([pump])
        pull(FINAL_LOAD_TIME if i == LOADS - 1 else LOAD_TIME)
    discard_tip()

    # ---------------- 3. Wash 1 ----------------
    pip.pick_up_tip()
    set_rates("wash")
    wash(WASH1_VOL, wash1)
    discard_tip()
    pull(WASH_TIME)

    # ---------------- 4. Wash 2 (x2) + dry ----------------
    heat = p.elution_temp > 0 and not dry
    if heat:
        temp_mod.start_set_temperature(p.elution_temp)  # ~30 min before elution
    pip.pick_up_tip()
    set_rates("wash")
    wash(WASH2_VOLS[0], wash2)
    pip.move_to(sample.top(PARK_Z))
    pull(WASH_TIME)
    wash(WASH2_VOLS[1], wash2)
    discard_tip()
    pull(WASH_TIME)
    pull(DRY_TIME)

    # ---------------- 5. Stack spin plate on elution plate, swap tips ----------------
    ctx.move_labware(collar, vm.manifold_dock, use_gripper=True)
    ctx.move_labware(
        spacer, vm, use_gripper=True,
        pick_up_offset={"x": 0, "y": 0, "z": SPACER_GRIP_RAISE},
        drop_offset={"x": MODULE_DROP_X, "y": 0, "z": SPACER_GRIP_RAISE},
    )
    ctx.move_labware(
        spin_plate, elution_plate, use_gripper=True,
        drop_offset={"x": MODULE_DROP_X, "y": 0, "z": 0},
    )
    ctx.move_labware(collar, vm, use_gripper=True)

    ctx.move_labware(racks[-1], "D2" if dry else chute, use_gripper=True)
    ctx.move_labware(elution_tips, tip_adapters["D1"], use_gripper=True)

    # ---------------- 6. Elution ----------------
    pip.pick_up_tip(elution_tips["A1"])
    set_rates("water")
    pip.flow_rate.blow_out = 10  # slow, so the blow-out doesn't spray the membrane
    if heat:
        temp_mod.await_temperature(p.elution_temp)
    pip.aspirate(p.elution_volume, water.bottom(ASP_Z))
    pip.dispense(p.elution_volume, spin.bottom(ELUTION_Z))
    pip.blow_out(spin.bottom(ELUTION_Z))
    discard_tip()
    if heat:
        temp_mod.deactivate()

    hold(ELUTION_SOAK)
    step = ELUTION_TIME // len(ELUTION_POWERS)
    for power in ELUTION_POWERS[:-1]:
        pull(step, power, vent=False)
    pull(ELUTION_TIME - step * (len(ELUTION_POWERS) - 1), ELUTION_POWERS[-1])
    ctx.comment("Done. Next, off-deck: HRC plate, 3,500 x g for 3 min (kit step 14).")
