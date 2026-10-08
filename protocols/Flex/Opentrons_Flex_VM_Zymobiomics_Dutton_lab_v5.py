"""
ZymoBIOMICS 96 DNA Kit on the Opentrons Flex + Vacuum Module (Dutton lab V6).

Deck
  A1 B1 D1  1000 uL tip racks on 96 adapters     C4  50 uL tip rack (elution)
  A2        sample plate, 400 uL lysate/well     B4  paper towel (blot, optional)
  B2 B3     Binding Buffer, Wash Buffer 1        A3  vacuum module + tall collar + spin plate
  C2 C3     Wash Buffer 2, water                 D2  tall spacer + elution plate
  D3        waste chute
  Reagents are in 12-well reservoirs: tip column k always lands in reservoir well k.

Partial plates (Sample Columns < 12)
  Full 96-tip pickup throughout, but every tip rack holds tips only in columns 1-N. The empty
  nozzles move with the head and never reach liquid, so only reservoir wells 1-N need reagent.
  Samples go in plate columns 1-N. Seal spin-plate columns N+1 to 12 so the vacuum doesn't
  pull air through their dry membranes.

Vacuum-on loading (from ZR-96 v2): lysate goes in low and slowly with the vacuum already
running, so it drains as it arrives and the binding-buffer salt line stays near the membrane.

Ends at elution. HRC inhibitor removal (kit step 14) is done off-deck.
"""

from opentrons import protocol_api, types

metadata = {
    "protocolName": "ZymoBIOMICS 96 DNA Kit - Flex + Vacuum Module (Dutton lab v6)",
    "author": "Tavis Goldwire",
    "description": "Spin-plate DNA extraction on the vacuum manifold, 8-96 samples, through elution.",
}

requirements = {"robotType": "Flex", "apiLevel": "2.30"}

# Labware
CUSTOM = {"namespace": "custom_beta", "version": 3}
RESERVOIR = "nest_12_reservoir_22ml"   
RESERVOIR_MAX = 15_000      # uL per reservoir well
WELL_MARGIN = 1_500         # uL left in each reservoir well after its last draw. Estimate, NOT validated:
                            # the well's V-bottom holds ~0.7 mL below 2 mm
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
    "lysate": (100, 15),    # dispense slower than the membrane drains under load vacuum (was 120)
    "wash": (150, 180),
    "water": (6, 10),       # aspirate was 20, too fast; 6 is the pipette's default for 50 uL tips
}
BLOWOUT_RATE = 100
ELUTION_BLOWOUT_RATE = 10
VISCOUS_DELAY_S = 2
BLOWOUT_DELAY_S = 5         # after dispensing into the spin plate, before blowing out

# Heights, mm
ASP_Z = 0.75                 # above well bottom, every 1000 uL tip aspiration
ELUTION_ASP_Z = 0.75         # water draw with the 50 uL tips (0.2 sealed them on the 1-well trough floor).
                            # NOT dry-run tested in the 12-well reservoir
MIX_DISP_Z = 12             # above well bottom
TOP_Z = -5                  # below well top, non-contact dispense and every blow-out
LOAD_Z = 3                  # above the spin plate definition's well bottom, lysate dispense under vacuum.
                            # ZR-96 v2's load height on the same plate and collar (MEMBRANE_Z + 5 + ON_COLLAR_DZ)
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
    # -350 mbar / 210 s drained the plate on 2026-09-23 but left 5 wells clogged on the next run.
    # -600 mbar / 600 s cleared them, so pull-through and dry default to that now.
    for key, name, default_pressure, default_time in (
        ("vac", "Pull-through", -600, 600),
        ("dry", "Membrane Dry", -600, 600),
        ("elution", "Elution Vacuum", -350, 240),
    ):
        p.add_int(
            variable_name=f"{key}_pressure",
            display_name=f"{name} Pressure",
            default=default_pressure,
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

    n = p.sample_columns

    def trough(slot, name, color, per_tip_ul):
        """12-well reservoir. Each tip column draws from its own well, 8 tips at a time, so
        wells 1-n get everything that column's tips take over the run, plus WELL_MARGIN."""
        reservoir = ctx.load_labware(RESERVOIR, slot, name)
        fill = 8 * per_tip_ul + WELL_MARGIN
        if fill > RESERVOIR_MAX:
            raise ValueError(f"{name} needs {fill} uL per well; the reservoir holds {RESERVOIR_MAX}.")
        liquid = ctx.define_liquid(name, "ZymoBIOMICS", color)
        for well in reservoir.wells()[:n]:
            well.load_liquid(liquid, fill)
        ctx.comment(f"Setup: {slot} {name}: {fill / 1000:.1f} mL in each of wells A1-A{n}")
        return reservoir["A1"]   # full pickup: aspirating at A1 puts tip column k in well k

    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 2 * BINDING_VOL)
    wash1 = trough("B3", "DNA Wash Buffer 1", "#FFFB00", WASH1_VOL)
    wash2 = trough("C2", "DNA Wash Buffer 2", "#00FF6E", sum(WASH2_VOLS))
    water = trough("C3", "Nuclease-free water", "#0048FF", p.elution_volume)
    lysate = ctx.define_liquid("Clarified lysate", "Operator-loaded", "#B266FF")
    for column in samples.parent.columns()[:n]:
        for well in column:
            well.load_liquid(lysate, 400)
    ctx.comment(
        f"{n} sample columns ({8 * n} samples): every tip rack holds tips in columns 1-{n} only. "
        f"Seal spin-plate columns {n + 1}-12." if n < 12 else "Full plate: 96 samples, full tip racks."
    )

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
        # Stops the pump without venting, as in ZR-96 v2 (worked on the ZR-96 cleanup run).
        vm.stop_vacuum_pump()
        ctx.wait_for_tasks([task])

    def set_rates(name):
        pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES[name]

    def discard_tip():
        if dry:
            pip.return_tip()
        else:
            pip.drop_tip(chute)

    def add(volume, source, dest, viscous=False, dest_z=None):
        # The air gap is in the tip too, so it is dispensed back out with the liquid.
        # dest_z: dispense that far above dest's bottom instead of from the top. The blow-out
        # stays at the top either way, above anything still pooled.
        pip.aspirate(volume, source.bottom(ASP_Z))
        if viscous:
            hold(VISCOUS_DELAY_S)
        pip.air_gap(AIR_GAP)
        pip.dispense(volume + AIR_GAP, dest.top(TOP_Z) if dest_z is None else dest.bottom(dest_z))
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

    # ---------------- 2. Load spin plate, vacuum on while dispensing ----------------
    # Vacuum starts before the aspirate so it has ramped by the time the tips reach the plate.
    set_rates("lysate")
    for _ in range(2):
        load_task = vacuum_on(p.load_pressure)
        add(LOAD_VOL, samples, spin_plate["A1"], viscous=True, dest_z=LOAD_Z)
        vacuum_off(load_task)
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
