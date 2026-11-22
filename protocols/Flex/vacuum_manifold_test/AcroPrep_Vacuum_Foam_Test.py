"""
AcroPrep vacuum foam test (Batman). Finds the lowest vacuum setting that pulls 400 uL of
Binding Buffer through the AcroPrep short-tip plate without foam reaching the collar.

Each trial: load binding buffer into plate columns 1-N with the vacuum OFF, pull at that
trial's setting for the full pull time, then pause so you can record the result.
Every trial reuses the same plate columns (membranes already wet).

Deck
  A3  vacuum module + tall collar + AcroPrep plate. Seal columns N+1 to 12.
  B3  12-well reservoir: Binding Buffer in wells 1-N (fill shown in the run log)
  C3  1000 uL tip rack directly on the deck, NO adapter (partial pickup). Uses column 1 only.
  D3  waste chute
  A2 B2 C2 must be EMPTY: with column-12 nozzles the 96-channel head hangs over the slot
  to the left of wherever it works.

Record per trial: seconds until all wells are empty, wells left with liquid, foam height.
"""

from opentrons import protocol_api
from opentrons.protocol_api import COLUMN

metadata = {
    "protocolName": "AcroPrep Vacuum Foam Test (Dutton lab)",
    "author": "Tavis Goldwire",
    "description": "Binding Buffer pull-through at up to 3 vacuum settings, column partial pickup.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.31"}

CUSTOM = {"namespace": "custom_beta", "version": 1}
SPIN_PLATE = "cytiva_96_wellplate_1000ul_shorttip_filter"
RESERVOIR = "nest_12_reservoir_22ml"
RESERVOIR_MAX = 15_000      # uL per reservoir well
WELL_MARGIN = 1_500         # uL left in each reservoir well after its last draw

ASP_Z = 0.75                # above reservoir bottom
DISP_TOP_Z = -5             # below spin-plate well top: no contact with the membrane
SAFE_Z = 20                 # above the reservoir, where the tips wait during each pull
AIR_GAP = 20
RATES = (80, 50)            # uL/s (aspirate, dispense). Slow dispense so the load itself doesn't froth


def add_parameters(p: protocol_api.ParameterContext):
    p.add_str(
        variable_name="mode",
        display_name="Vacuum Mode",
        description="Power = fixed pump %. Pressure = module holds a set mbar.",
        default="power",
        choices=[
            {"display_name": "Pump power (%)", "value": "power"},
            {"display_name": "Pressure (mbar)", "value": "pressure"},
        ],
    )
    for i, default in ((1, 30), (2, 50), (3, 70)):
        p.add_int(
            variable_name=f"setting_{i}",
            display_name=f"Trial {i} Setting",
            description="Power mode: % (1-100). Pressure mode: mbar below atmosphere (1-800). 0 = skip.",
            default=default,
            minimum=0,
            maximum=800,
        )
    p.add_int(
        variable_name="columns",
        display_name="Plate Columns",
        description="Columns 1 to this number get loaded. Match the real run (6 = 48 wells).",
        default=6,
        minimum=1,
        maximum=12,
    )
    p.add_int(
        variable_name="load_volume",
        display_name="Load Volume",
        description="Binding Buffer per well per trial.",
        default=400,
        minimum=100,
        maximum=900,
        unit="uL",
    )
    p.add_int(
        variable_name="pull_time",
        display_name="Pull Time",
        description="Vacuum on per trial. Keep it running after wells empty: that is when foam forms.",
        default=300,
        minimum=30,
        maximum=900,
        unit="s",
    )


def run(ctx: protocol_api.ProtocolContext):
    p = ctx.params
    n = p.columns
    settings = [s for s in (p.setting_1, p.setting_2, p.setting_3) if s > 0]
    if not settings:
        raise ValueError("All three trial settings are 0; set at least one.")
    if p.mode == "power" and max(settings) > 100:
        raise ValueError(f"Power mode takes 1-100 %; got {max(settings)}.")

    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    plate = collar.load_labware(SPIN_PLATE, "AcroPrep plate", **CUSTOM)
    reservoir = ctx.load_labware(RESERVOIR, "B3", "Binding Buffer")
    tips = ctx.load_labware("opentrons_flex_96_tiprack_1000ul", "C3", "1000 uL tips (no adapter)")

    pip = ctx.load_instrument("flex_96channel_1000", "left")
    pip.configure_nozzle_layout(style=COLUMN, start="A12", tip_racks=[tips])
    pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES

    per_well = len(settings) * 8 * p.load_volume + WELL_MARGIN
    if per_well > RESERVOIR_MAX:
        raise ValueError(
            f"Each reservoir well needs {per_well} uL; it holds {RESERVOIR_MAX}. "
            "Use fewer trials or a smaller load volume."
        )
    buffer = ctx.define_liquid("Binding Buffer", "ZymoBIOMICS DNA Binding Buffer", "#FF0000")
    for well in reservoir.wells()[:n]:
        well.load_liquid(buffer, per_well)
    unit = "%" if p.mode == "power" else "mbar below atmosphere"
    ctx.comment(
        f"Setup: reservoir wells 1-{n}, {per_well / 1000:.1f} mL each "
        f"({n * per_well / 1000:.1f} mL Binding Buffer total). Trials: {settings} {unit}."
    )

    # ---------------- Helpers ----------------
    def pull(setting):
        vm.close_vent()
        if p.mode == "power":
            task = vm.start_set_vacuum_power(
                setting, p.pull_time, vent_after=True, equalize_timeout_s=20
            )
        else:
            task = vm.start_set_vacuum_pressure(
                -setting, p.pull_time, vent_after=True, equalize_timeout_s=20
            )
        ctx.wait_for_tasks([task])

    # ---------------- Trials ----------------
    # One column of tips for the whole test: it only ever touches Binding Buffer.
    pip.pick_up_tip()
    for t, setting in enumerate(settings, start=1):
        ctx.comment(f"----- Trial {t}: {setting} {unit} -----")
        for col in range(1, n + 1):
            pip.aspirate(p.load_volume, reservoir[f"A{col}"].bottom(ASP_Z))
            pip.air_gap(AIR_GAP)
            pip.dispense(p.load_volume + AIR_GAP, plate[f"A{col}"].top(DISP_TOP_Z))
            pip.blow_out(plate[f"A{col}"].top(DISP_TOP_Z))
        pip.move_to(reservoir["A1"].top(SAFE_Z))
        pull(setting)
        ctx.pause(
            f"Trial {t} ({setting} {unit}) done. Record: time until all wells empty, "
            "wells left with liquid, foam height. Resume for the next trial."
        )
    pip.drop_tip(chute)
    ctx.comment("Test done.")
