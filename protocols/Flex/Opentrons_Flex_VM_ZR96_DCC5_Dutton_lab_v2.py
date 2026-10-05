"""
ZR-96 DNA Clean & Concentrator-5 (Zymo D4023/D4024) on the Opentrons Flex + Vacuum Module
(Dutton lab v2). Built from the ZymoBIOMICS 96 vacuum protocol (v6): same deck hardware,
vacuum helper, blot, and elution-plate swap.

Deck
  A1        1000 uL tips (bind + load)        A3  vacuum module + tall collar + spin plate
  B1        1000 uL tips (washes)             D2  tall spacer + elution plate
  D1        50 uL tips (elution)              B4  paper towel (blot, optional)
  A2        PCR plate, DNA samples            D3  waste chute
  B2 B3 C3  Binding Buffer, Wash Buffer, water
  (all three tip racks sit on 96-tip adapters; C1, C2 empty)

Kit steps -> protocol
  1  Binding Buffer into the sample wells, mix          (kit: vortex)
  2-3 Load spin plate under gentle vacuum, then pull    (kit: 5 min spin)
  4  300 uL wash, vacuum, 300 uL wash, vacuum, dry      (kit: 5 min + 15 min spins)

Wall contact (v2)
  Binding Buffer leaves salt wherever it touches, so it goes in low and slowly with the vacuum
  already running: it drains as it arrives and the salt line stays near the membrane.
  The washes go in with the vacuum OFF so they pool above that salt line and rinse it,
  dispensed just above their own pooled level instead of from the top of the well.
  Elution water goes in low with the vacuum off and soaks before the pull.
  5  Blot, stack on elution plate, water, vacuum elute  (kit: 3 min spin)
"""

from opentrons import protocol_api, types

metadata = {
    "protocolName": "ZR-96 DNA Clean & Concentrator-5 - Flex + Vacuum Module (Dutton lab v2)",
    "author": "Tavis Goldwire",
    "description": "96-well DNA cleanup on the vacuum manifold: bind, two washes, dry, elute.",
}

requirements = {"robotType": "Flex", "apiLevel": "2.30"}

# Labware
CUSTOM = {"namespace": "custom_beta", "version": 3}
RESERVOIR = "nest_1_reservoir_290ml"
SAMPLE_PLATE = "opentrons_96_wellplate_200ul_pcr_full_skirt"
TIPRACK = "opentrons_flex_96_tiprack_1000ul"
ELUTION_TIPRACK = "opentrons_flex_96_tiprack_50ul"

# Volumes, uL per well
MIN_BINDING_VOL = 100       # kit footnote 1: at least 100 uL Binding Buffer for samples <= 50 uL
PCR_WELL_MAX = 180          # sample + binding must fit the 200 uL PCR well with room to mix
WASH_VOL = 300              # kit step 4, done twice
MIX_REPS = 10
AIR_GAP = 20                # not used at elution: 50 uL tips have no room for one
TROUGH_MARGIN = 35_000      # fill = use + this. Matches the ~35-40 mL overage in the v6 troughs

# Flow rates, uL/s per channel: (aspirate, dispense)
RATES = {
    "binding": (80, 80),
    "mix": (100, 100),
    "load": (60, 15),       # dispense slower than the membrane drains under load vacuum
    "wash": (150, 50),      # slow enough not to splash up the walls
    "water": (20, 10),
}
BLOWOUT_RATE = 100
SPIN_BLOWOUT_RATE = 20      # gentler air puff into the spin plate so it doesn't spray droplets up the walls
ELUTION_BLOWOUT_RATE = 10
VISCOUS_DELAY_S = 2
BLOWOUT_DELAY_S = 5         # after dispensing into the spin plate, before blowing out

# Heights, mm
ASP_Z = 1.0                 # above well bottom, every 1000 uL tip aspiration (0.2 tripped overpressure, v6)
ELUTION_ASP_Z = 0.4         # water draw with the 50 uL tips (0.2 sealed them on the trough floor)
PCR_TOP_Z = -2              # below PCR well top, Binding Buffer dispense
MIX_DISP_Z = 4              # above PCR well bottom
# Spin-plate heights all hang off MEMBRANE_Z, so one measurement sets every dispense.
MEMBRANE_Z = 2              # UNMEASURED. Membrane surface above zymo_96_spin_plate.json's well bottom
                            # (the definition puts that at the lowest point of the plate, likely the nozzle
                            # tip). 2 reproduces v1's ELUTION_Z of 4. Measure, set, then tune the offsets.
ELUTION_Z = MEMBRANE_Z + 2  # water lands on the membrane, touches nothing else
LOAD_Z = MEMBRANE_Z + 5     # above the ~3 mm a 150 uL load would pool to; under vacuum it stays lower
WASH_Z = MEMBRANE_Z + 10    # above the ~6 mm 300 uL pools to: tip never touches the wash,
                            # so one tip can do both washes without carrying well contents to the trough
WASH_CLEARANCE = 2          # mm the wash tip must stay above the estimated pooled wash level

# Gripper (unchanged from v6)
SPACER_GRIP_RAISE = 5
MODULE_DROP_X = -1.0
GRIP_FORCE = 15
TRAVEL_Z = 150
BLOT_Z = 1.5
BLOT_SPEED = 10
BLOT_CONTACT_S = 10

DRY_SHORT_VAC_S = 5


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
        variable_name="sample_volume",
        display_name="Sample Volume",
        description="DNA sample already in each PCR plate well.",
        default=50,
        minimum=10,
        maximum=60,
        unit="uL",
    )
    p.add_int(
        variable_name="binding_ratio",
        display_name="Binding Buffer Ratio",
        description="Binding Buffer : sample (kit step 1). Never less than 100 uL.",
        default=2,
        choices=[
            {"display_name": "2:1 (genomic / plasmid DNA)", "value": 2},
            {"display_name": "5:1 (PCR product, fragments)", "value": 5},
        ],
    )
    p.add_str(
        variable_name="elution_mode",
        display_name="Elution",
        description="Vacuum elution on deck, or stop after drying and elute in the centrifuge.",
        default="vacuum",
        choices=[
            {"display_name": "Vacuum (on deck)", "value": "vacuum"},
            {"display_name": "Centrifuge (stop after dry)", "value": "centrifuge"},
        ],
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
        description="Water per well, delivered with 50 uL tips. Kit minimum is 10 uL.",
        default=20.0,
        minimum=10.0,
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
        description="Gentle vacuum held while the sample is dispensed. Tune against yield.",
        default=-125,
        minimum=-350,
        maximum=-50,
        unit="mbar",
    )
    # Floors carried over from v6 (-350 mbar / 210 s drained 800 uL of lysate, 2026-09-23).
    # Volumes here are smaller, so these are conservative; validate before shortening.
    for key, name, default_time in (
        ("vac", "Pull-through", 210),
        ("dry", "Membrane Dry", 600),
        ("elution", "Elution Vacuum", 240),
    ):
        p.add_int(
            variable_name=f"{key}_pressure",
            display_name=f"{name} Pressure",
            default=-350,
            minimum=-800,
            maximum=-350,
            unit="mbar",
        )
        p.add_int(
            variable_name=f"{key}_time",
            display_name=f"{name} Time",
            default=default_time,
            minimum=210,
            maximum=900,
            unit="s",
        )


def run(ctx: protocol_api.ProtocolContext):
    p = ctx.params
    dry = p.run_mode != "real"
    vacuum_elution = p.elution_mode == "vacuum"

    sample_vol = p.sample_volume
    binding_vol = max(MIN_BINDING_VOL, p.binding_ratio * sample_vol)
    load_vol = sample_vol + binding_vol
    if load_vol > PCR_WELL_MAX:
        raise ValueError(
            f"{sample_vol} uL sample + {binding_vol} uL Binding Buffer = {load_vol} uL, "
            f"over the {PCR_WELL_MAX} uL PCR-well limit. Lower the sample volume."
        )
    mix_vol = round(0.8 * load_vol)

    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    spin_plate = collar.load_labware("zymo_96_spin_plate", "Zymo-Spin I-96 Plate", **CUSTOM)
    spacer = ctx.load_adapter("custom_vacuum_manifold_spacer_tall", "D2", **CUSTOM)
    elution_plate = spacer.load_labware("elution_plate_placeholder", "Elution plate", **CUSTOM)
    samples = ctx.load_labware(SAMPLE_PLATE, "A2", "DNA samples")["A1"]

    bind_rack = ctx.load_adapter("opentrons_flex_96_tiprack_adapter", "A1").load_labware(TIPRACK)
    wash_rack = ctx.load_adapter("opentrons_flex_96_tiprack_adapter", "B1").load_labware(TIPRACK)
    elution_tips = ctx.load_adapter("opentrons_flex_96_tiprack_adapter", "D1").load_labware(
        ELUTION_TIPRACK, "50 uL tips for elution"
    )
    pad = ctx.load_labware("dutton_blot_pad", "B4", "Blot towel", **CUSTOM) if p.blot else None

    # Full pickup; every pick_up_tip names its rack, so automatic tip tracking never decides.
    pip = ctx.load_instrument("flex_96channel_1000", "left", tip_racks=[bind_rack, wash_rack])

    def trough(slot, name, color, use_ul):
        fill = round(use_ul + TROUGH_MARGIN)
        well = ctx.load_labware(RESERVOIR, slot, name)["A1"]
        well.load_liquid(ctx.define_liquid(name, "ZR-96 DCC-5", color), fill)
        ctx.comment(f"Setup: {slot} {name}: {fill / 1000:.1f} mL")
        return well

    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 96 * binding_vol)
    wash = trough("B3", "DNA Wash Buffer (ethanol added)", "#FFFB00", 96 * 2 * WASH_VOL)
    water = trough("C3", "Nuclease-free water", "#0048FF", 96 * p.elution_volume)
    dna = ctx.define_liquid("DNA sample", "Operator-loaded", "#B266FF")
    for well in samples.parent.wells():
        well.load_liquid(dna, sample_vol)

    # ---------------- Helpers ----------------
    def hold(seconds):
        if not dry and seconds > 0:
            ctx.delay(seconds=seconds)

    def vacuum(pressure, seconds):
        if p.run_mode == "dry_short":
            seconds = DRY_SHORT_VAC_S
        vm.close_vent()
        task = vm.start_set_vacuum_pressure(pressure, seconds, vent_after=True, equalize_timeout_s=20)
        ctx.wait_for_tasks([task])

    def vacuum_on(pressure):
        """Hold vacuum with no end time; the protocol keeps running. End with vacuum_off()."""
        vm.close_vent()
        return vm.start_set_vacuum_pressure(pressure)

    def vacuum_off(task):
        # Stops the pump without venting, so the pull-through that follows starts from vacuum.
        # Behaviour of stop_vacuum_pump() on an open-ended hold is simulated only; confirm on hardware.
        vm.stop_vacuum_pump()
        ctx.wait_for_tasks([task])

    def set_rates(name):
        pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES[name]

    def discard_tip():
        if dry:
            pip.return_tip()
        else:
            pip.drop_tip(chute)

    def add(volume, source, dest, viscous=False):
        """source/dest are Locations. The air gap goes out with the liquid."""
        pip.aspirate(volume, source)
        if viscous:
            hold(VISCOUS_DELAY_S)
        pip.air_gap(AIR_GAP)
        pip.dispense(volume + AIR_GAP, dest)
        # Location.labware wraps the target; unwrap to the Well to compare plates. (v1 compared the
        # wrapper's .parent with `is`, which was never True, so this pause never ran.)
        if dest.labware.as_well().parent == spin_plate:
            hold(BLOWOUT_DELAY_S)
            pip.flow_rate.blow_out = SPIN_BLOWOUT_RATE
        else:
            pip.flow_rate.blow_out = BLOWOUT_RATE
        pip.blow_out(dest)

    def blot():
        """Unchanged from v6: grip the spin plate in the docked collar, touch it to the B4
        towel, and set it back. The gripper never lets go on the towel."""
        a1, h12 = spin_plate["A1"].center().point, spin_plate["H12"].center().point
        bottom = spin_plate.calibrated_offset.z
        grip_height = (spin_plate.highest_z - bottom) / 2
        grip = types.Point((a1.x + h12.x) / 2, (a1.y + h12.y) / 2, bottom + grip_height)

        pad_xy = pad["A1"].center().point
        slot_surface_z = pad.calibrated_offset.z
        touch = types.Point(pad_xy.x, pad_xy.y, slot_surface_z + BLOT_Z + grip_height)
        above_grip = grip._replace(z=TRAVEL_Z)
        above_pad = touch._replace(z=TRAVEL_Z)

        def go(point, speed=None):
            ctx.robot.move_to("gripper", types.Location(point, None), speed=speed)

        ctx.robot.open_gripper_jaw()
        go(above_grip)
        go(grip)
        ctx.robot.close_gripper_jaw(GRIP_FORCE)
        go(above_grip)
        go(above_pad)
        go(touch, BLOT_SPEED)
        hold(BLOT_CONTACT_S)
        go(above_pad, BLOT_SPEED)
        go(above_grip)
        go(grip, BLOT_SPEED)
        ctx.robot.open_gripper_jaw()
        go(above_grip)

    # Wash tip must clear the pooled wash. Estimate uses the definition's 8 mm well diameter;
    # if the real column tapers, the true level is higher, so keep some clearance.
    well_area = 3.14159 * (spin_plate["A1"].diameter / 2) ** 2
    wash_level = WASH_VOL / well_area
    if WASH_Z - MEMBRANE_Z < wash_level + WASH_CLEARANCE:
        raise ValueError(
            f"WASH_Z is {WASH_Z - MEMBRANE_Z} mm above the membrane; 300 uL pools to ~{wash_level:.1f} mm. "
            f"Raise WASH_Z to at least {wash_level + WASH_CLEARANCE:.1f} mm above the membrane."
        )

    ctx.comment(
        f"Sample {sample_vol} uL + Binding Buffer {binding_vol} uL = {load_vol} uL/well; "
        f"elution {p.elution_volume} uL ({p.elution_mode})"
    )

    # ---------------- 1. Binding Buffer + mix (kit step 1) ----------------
    pip.pick_up_tip(bind_rack["A1"])
    pip.flow_rate.blow_out = BLOWOUT_RATE   # for the post-mix blow-out; add() sets its own
    set_rates("binding")
    add(binding_vol, binding.bottom(ASP_Z), samples.top(PCR_TOP_Z), viscous=True)

    set_rates("mix")
    for _ in range(MIX_REPS):
        pip.aspirate(mix_vol, samples.bottom(ASP_Z))
        pip.dispense(mix_vol, samples.bottom(MIX_DISP_Z))
    pip.blow_out(samples.top(PCR_TOP_Z))

    # ---------------- 2-3. Load under gentle vacuum, then pull through (kit steps 2-3) ----------------
    # Vacuum starts before the aspirate so it has ramped by the time the tips reach the plate.
    # Aspirates the full nominal volume; whatever the PCR well keeps behind is the loss.
    set_rates("load")
    load_task = vacuum_on(p.load_pressure)
    add(load_vol, samples.bottom(ASP_Z), spin_plate["A1"].bottom(LOAD_Z), viscous=True)
    discard_tip()
    vacuum_off(load_task)
    vacuum(p.vac_pressure, p.vac_time)

    # ---------------- 4. Two 300 uL washes + dry (kit step 4) ----------------
    # Vacuum OFF while dispensing so each wash pools above the salt line before it is pulled.
    # Dispensed at WASH_Z, above the pooled level: no tip contact, so one tip serves both washes.
    pip.pick_up_tip(wash_rack["A1"])
    set_rates("wash")
    add(WASH_VOL, wash.bottom(ASP_Z), spin_plate["A1"].bottom(WASH_Z))
    vacuum(p.vac_pressure, p.vac_time)
    add(WASH_VOL, wash.bottom(ASP_Z), spin_plate["A1"].bottom(WASH_Z))
    discard_tip()
    vacuum(p.vac_pressure, p.vac_time)
    vacuum(p.dry_pressure, p.dry_time)   # stands in for the kit's 15 min second-wash spin

    if not vacuum_elution:
        ctx.comment(
            f"Stopped before elution. Off-deck: spin plate onto the Elution Plate, add "
            f"{p.elution_volume} uL water, wait 1 min, centrifuge 3 min at 3,000-5,000 x g (kit step 5)."
        )
        return

    # ---------------- 5. Blot, stack on elution plate, elute (kit step 5) ----------------
    ctx.move_labware(collar, vm.manifold_dock, use_gripper=True)
    if pad:
        blot()
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

    pip.pick_up_tip(elution_tips["A1"])
    set_rates("water")
    pip.flow_rate.blow_out = ELUTION_BLOWOUT_RATE
    pip.aspirate(p.elution_volume, water.bottom(ELUTION_ASP_Z))
    pip.dispense(p.elution_volume, spin_plate["A1"].bottom(ELUTION_Z))
    hold(BLOWOUT_DELAY_S)
    pip.blow_out(spin_plate["A1"].bottom(ELUTION_Z))
    discard_tip()

    hold(p.elution_incubation)
    vacuum(p.elution_pressure, p.elution_time)
    ctx.comment("Done. Cleaned DNA is in the elution plate on the vacuum module.")
