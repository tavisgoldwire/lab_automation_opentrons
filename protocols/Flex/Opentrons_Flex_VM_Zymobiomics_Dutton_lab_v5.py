"""
ZymoBIOMICS 96 DNA Kit on the Opentrons Flex + Vacuum Module (Dutton lab V5).

Deck
  A1 B1 D1  1000 uL tip racks on 96 adapters     C4  50 uL tip rack (elution)
  A2        sample plate, 400 uL lysate/well     B4  paper towel (blot, optional)
  B2 B3     Binding Buffer, Wash Buffer 1        A3  vacuum module + tall collar + spin plate
  C2 C3     Wash Buffer 2, water                 D2  tall spacer + elution plate
  D3        waste chute

Ends at elution. HRC inhibitor removal (kit step 14) is done off-deck.
"""

from opentrons import protocol_api, types

metadata = {
    "protocolName": "ZymoBIOMICS 96 DNA Kit - Flex + Vacuum Module (Dutton lab v5)",
    "author": "Tavis Goldwire",
    "description": "96-well spin-plate DNA extraction on the vacuum manifold, through elution.",
}

requirements = {"robotType": "Flex", "apiLevel": "2.30"}

# Labware
CUSTOM = {"namespace": "custom_beta", "version": 3}
RESERVOIR = "nest_1_reservoir_290ml"
TIPRACK = "opentrons_flex_96_tiprack_1000ul"
ELUTION_TIPRACK = "opentrons_flex_96_tiprack_50ul"

# Volumes, uL per well
BINDING_VOL = 600           # added twice
LOAD_VOL = 800              # 400 lysate + 1200 binding, moved twice
WASH1_VOL = 400
WASH2_VOLS = (700, 200)
MIX_VOL = 900
MIX_REPS = 6
AIR_GAP = 20                # not used at elution: 50 uL tips have no room for one

# Flow rates, uL/s per channel: (aspirate, dispense)
RATES = {
    "binding": (80, 150),
    "mix": (150, 150),
    "lysate": (100, 120),
    "wash": (150, 180),
    "water": (20, 10),
}
BLOWOUT_RATE = 100
ELUTION_BLOWOUT_RATE = 10
VISCOUS_DELAY_S = 2
BLOWOUT_DELAY_S = 5         # after dispensing into the spin plate, before blowing out

# Heights, mm
ASP_Z = 0.75                 # above well bottom, every 1000 uL tip aspiration
ELUTION_ASP_Z = 0.4         # water draw with the 50 uL tips (0.2 sealed them on the trough floor)
MIX_DISP_Z = 12             # above well bottom
TOP_Z = -5                  # below well top, non-contact dispense
ELUTION_Z = 4               # above the definition's well bottom. zymo_96_spin_plate.json puts that
                            # at the lowest point of the plate; if that is the drip nozzle, set this to
                            # (nozzle tip to membrane) + 2 mm, measured on a plate, before a real run

# Gripper
SPACER_GRIP_RAISE = 5       # mm above default grip, clears the manifold rim
MODULE_DROP_X = -1.0        # drops on the vacuum module landed ~1 mm right; shift them left
GRIP_FORCE = 15             # N (Opentrons default for labware)
TRAVEL_Z = 150              # gripper jaw height while carrying the plate to the towel (homes at ~166)
BLOT_Z = 1.5                # plate bottom above the B4 slot surface at contact; lower in 0.5 mm steps.
                            # Referenced to the slot, not the towel: the pad definition's height is not used
BLOT_SPEED = 10             # mm/s, descent onto and lift off the towel
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
    # -350 mbar / 210 s fully drained the plate (2026-09-23), so it is the weakest/shortest allowed.
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

    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    spin_plate = collar.load_labware("zymo_96_spin_plate", "Zymo-Spin I-96-Z Plate", **CUSTOM)
    spacer = ctx.load_adapter("custom_vacuum_manifold_spacer_tall", "D2", **CUSTOM)
    elution_plate = spacer.load_labware("elution_plate_placeholder", "Elution plate", **CUSTOM)
    samples = ctx.load_labware("nest_96_wellplate_2ml_deep", "A2", "Samples")["A1"]

    tip_adapters = {s: ctx.load_adapter("opentrons_flex_96_tiprack_adapter", s) for s in ("A1", "B1", "D1")}
    racks = [adapter.load_labware(TIPRACK) for adapter in tip_adapters.values()]
    elution_tips = ctx.load_labware(ELUTION_TIPRACK, "C4", "50 uL tips for elution")
    pad = ctx.load_labware("dutton_blot_pad", "B4", "Blot towel", **CUSTOM) if p.blot else None

    pip = ctx.load_instrument("flex_96channel_1000", "left", tip_racks=racks)  # full pickup: A1 = whole plate

    def trough(slot, name, color, fill_ul):
        well = ctx.load_labware(RESERVOIR, slot, name)["A1"]
        well.load_liquid(ctx.define_liquid(name, "ZymoBIOMICS", color), fill_ul)
        return well

    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 150_000)
    wash1 = trough("B3", "DNA Wash Buffer 1", "#FFFB00", 80_000)
    wash2 = trough("C2", "DNA Wash Buffer 2", "#00FF6E", 150_000)
    water = trough("C3", "Nuclease-free water", "#0048FF", 40_000)
    lysate = ctx.define_liquid("Clarified lysate", "Operator-loaded", "#B266FF")
    for well in samples.parent.wells():
        well.load_liquid(lysate, 400)

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

    def set_rates(name):
        pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES[name]

    def discard_tip():
        if dry:
            pip.return_tip()
        else:
            pip.drop_tip(chute)

    def add(volume, source, dest, viscous=False):
        # The air gap is in the tip too, so it is dispensed back out with the liquid.
        pip.aspirate(volume, source.bottom(ASP_Z))
        if viscous:
            hold(VISCOUS_DELAY_S)
        pip.air_gap(AIR_GAP)
        pip.dispense(volume + AIR_GAP, dest.top(TOP_Z))
        if dest.parent is spin_plate:
            hold(BLOWOUT_DELAY_S)
        pip.blow_out(dest.top(TOP_Z))

    def blot():
        """Grip the spin plate in the docked collar, lower it slowly onto the B4 towel,
        lift it, and set it back in the collar. The gripper never lets go on the towel."""
        a1, h12 = spin_plate["A1"].center().point, spin_plate["H12"].center().point
        bottom = spin_plate.calibrated_offset.z
        grip_height = (spin_plate.highest_z - bottom) / 2  # same grip height move_labware uses
        grip = types.Point((a1.x + h12.x) / 2, (a1.y + h12.y) / 2, bottom + grip_height)

        pad_xy = pad["A1"].center().point
        slot_surface_z = pad.calibrated_offset.z  # B4 slot surface (labware origin)
        touch = types.Point(pad_xy.x, pad_xy.y, slot_surface_z + BLOT_Z + grip_height)
        above_grip = grip._replace(z=TRAVEL_Z)
        above_pad = touch._replace(z=TRAVEL_Z)

        def go(point, speed=None):
            ctx.robot.move_to("gripper", types.Location(point, None), speed=speed)

        # Every lateral move happens at TRAVEL_Z: straight up out of the collar, across, straight down.
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

    # ---------------- 1. Binding buffer + mix ----------------
    pip.pick_up_tip()
    pip.flow_rate.blow_out = BLOWOUT_RATE
    set_rates("binding")
    for _ in range(2):
        add(BINDING_VOL, binding, samples, viscous=True)

    set_rates("mix")
    for _ in range(MIX_REPS):
        pip.aspirate(MIX_VOL, samples.bottom(ASP_Z))
        pip.dispense(MIX_VOL, samples.bottom(MIX_DISP_Z))
    pip.blow_out(samples.top(TOP_Z))

    # ---------------- 2. Load spin plate ----------------
    set_rates("lysate")
    for _ in range(2):
        add(LOAD_VOL, samples, spin_plate["A1"], viscous=True)
        vacuum(p.vac_pressure, p.vac_time)
    discard_tip()

    # ---------------- 3. Wash 1 ----------------
    pip.pick_up_tip()
    set_rates("wash")
    add(WASH1_VOL, wash1, spin_plate["A1"])
    discard_tip()
    vacuum(p.vac_pressure, p.vac_time)

    # ---------------- 4. Wash 2 (x2) + dry ----------------
    pip.pick_up_tip()
    set_rates("wash")
    add(WASH2_VOLS[0], wash2, spin_plate["A1"])
    vacuum(p.vac_pressure, p.vac_time)
    add(WASH2_VOLS[1], wash2, spin_plate["A1"])
    discard_tip()
    vacuum(p.vac_pressure, p.vac_time)
    vacuum(p.dry_pressure, p.dry_time)

    # ---------------- 5. Blot, stack for elution, swap tips ----------------
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

    # Dry runs returned their tips to the D1 rack: park it in D2 (empty now the spacer has moved).
    ctx.move_labware(racks[-1], "D2" if dry else chute, use_gripper=True)
    ctx.move_labware(elution_tips, tip_adapters["D1"], use_gripper=True)

    # ---------------- 6. Elution ----------------
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
    ctx.comment("Done. Next, off-deck: HRC plate, 3,500 x g for 3 min (kit step 14).")
