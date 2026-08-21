from opentrons import protocol_api
from opentrons import types
from opentrons.protocol_api import COLUMN, ALL

metadata = {
    'protocolName': 'Select-a-Size DNA Clean & Concentrator Kit',
    'author': 'Tavis Goldwire',
    'description': 'Select-a-Size DNA Clean & Concentrator Kit designed for post PCR clean up.',
    'source': 'Tavis'
}


requirements = {
    'robotType': 'Flex',
    'apiLevel': '2.29'
}


def add_parameters(parameters):
    parameters.add_float(
        display_name="MagBead Incubation (min)",
        variable_name="magbead_incubation_time",
        description="The time in minutes for the magnetic bead incubation step.",
        default=5.0,
        minimum=1.0,
        maximum=30.0
    )
    parameters.add_float(
        display_name="Bead Mixing Volume (µL)",
        variable_name="bead_mixing_volume",
        description="Volume in µL to use for magnetic bead mixing operations.",
        default=200.0,
        minimum=50.0,
        maximum=800.0
    )
    parameters.add_bool(
        display_name="Dry Run",
        variable_name="DryRun",
        description="A dry run will skip all delays and speed up movements.",
        default=False
    )






def run(protocol: protocol_api.ProtocolContext):

    # PARAMETERS
    magbead_incubation_time = protocol.params.magbead_incubation_time
    bead_mixing_volume = protocol.params.bead_mixing_volume
    DryRun = protocol.params.DryRun


    # PIPETTES
    pip96 = protocol.load_instrument("flex_96channel_200")
    #pip96.configure_nozzle_layout(style=COLUMN, start="A12", tip_racks=[mixing_tips_1000])
    

# FIXTURES & MODULES
    # Changed from trash bin to waste chute (fixed in slot D3)
    waste_chute = protocol.load_waste_chute()
    temp_module = protocol.load_module('temperature module gen2', 'A3')
    temp_adapter = temp_module.load_adapter('opentrons_96_well_aluminum_block')
    mag_block = protocol.load_module('magneticBlockV1', 'C1') 
    heater_shaker = protocol.load_module('heaterShakerModuleV1', 'D1')


# LABWARE
    transfer_tips_200 = protocol.load_labware('opentrons_flex_96_tiprack_200ul', 'A1') #tips used for prepping reagents

    full_adapter = protocol.load_adapter('opentrons_flex_96_tiprack_adapter', 'C2')
    magbead_tips_200 = full_adapter.load_labware('opentrons_flex_96_tiprack_200ul')

    wash_tips_50 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'B1')
    elution_tips_50 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'B2')
    sample_plate = temp_adapter.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt')
    final_elution_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 'B3')
    reagent_reservoir = protocol.load_labware('nest_12_reservoir_15ml', 'D2')
    waste_reservoir = protocol.load_labware('nest_1_reservoir_195ml', 'C3')

    # LIQUIDS
    dnase_free_water = reagent_reservoir.wells()[0]
    dna_wash_buffer = reagent_reservoir.wells()[2]
    water_magbead_mix = reagent_reservoir.wells()[11]
    waste = waste_reservoir.wells()[0]

    # Define liquids
    water_liquid = protocol.define_liquid("DNase Free Water", "DNase free water", "#0000FF")
    wash_buffer_liquid = protocol.define_liquid("DNA Wash Buffer", "Wash buffer", "#00FF00")
    water_magbead_liquid = protocol.define_liquid("Water + Magnetic Beads", "Water + beads", "#8B4513")

    dnase_free_water.load_liquid(water_liquid, 3000)
    dna_wash_buffer.load_liquid(wash_buffer_liquid, 6000)
    water_magbead_mix.load_liquid(water_magbead_liquid, 3347.5)

    sample_columns = sample_plate.columns()
    elution_columns = final_elution_plate.columns()


    # FUNCTIONS
    #drop tips
    def drop_tip(pipette):
        pipette.return_tip() if DryRun else pipette.drop_tip(waste_chute)


# START
    protocol.comment('------STARTING PROTOCOL------')
    protocol.comment('STEP 1: Pre-mix magnetic bead reservoir')

    #partial pick up of 8 channel
    pip96.configure_nozzle_layout(style=COLUMN, start="A12", tip_racks=[transfer_tips_200])
    pip96.pick_up_tip(transfer_tips_200.columns()[0][0]) #grab tips with large pipette


    #pip96.mix(repetitions=5, volume=200, location=water_magbead_mix, rate=1.0)
    pip96.mix(repetitions=5, volume=150, location=water_magbead_mix, rate=1.5)
    pip96.blow_out(water_magbead_mix)

    protocol.comment('STEP 2: Dispense Magbeads')

    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        pip96.aspirate(26, water_magbead_mix.bottom(0.3), rate=0.5) #draw up mag bead mix slow
        pip96.dispense(26, current_column[0].top()) #dispense in samples without touching samples
        pip96.blow_out(current_column[0].top(2)) #blow out residue

        if col_idx == 6: #midpoint mix
            pip96.mix(repetitions=5, volume=100, location=water_magbead_mix, rate=1.5)
            pip96.blow_out(water_magbead_mix)

    drop_tip(pip96) #drop tips

    protocol.comment('STEP 3: Mix Samples')

    pip96.configure_nozzle_layout(style=ALL, tip_racks=[magbead_tips_200]) #get full tips
    pip96.pick_up_tip()
    pip96.mix(volume=100, location=sample_plate["A1"], repetitions=10) #mix up the sample with magbeads
    pip96.mix(volume=100, location=sample_plate["A1"], repetitions=10, aspirate_flow_rate=50, dispense_flow_rate=50) #slower mix after
    pip96.blow_out(sample_plate["A1"].top()) #blow out residuals
    pip96.return_tip()

    # Incubate
    protocol.comment('STEP 4: Incubate samples at room temp')
    protocol.delay(minutes=5 if not DryRun else 0.5)


    # STEP 5: Move to magnet
    protocol.comment('STEP 5: Move to magnet')
    protocol.move_labware(sample_plate, mag_block, use_gripper=True)

    # STEP 6: Magnetic separation
    protocol.comment('STEP 6: Magnet incubation')
    protocol.delay(minutes=magbead_incubation_time if not DryRun else 0.5)

     # STEP 7: Remove supernatant
    protocol.comment('STEP 8: Remove supernatant')

    pip96.configure_nozzle_layout(style=ALL, tip_racks=[magbead_tips_200]) #get full tips
    pip96.pick_up_tip()

    pip96.configure_nozzle_layout(style=COLUMN, start="B12", tip_racks=[transfer_tips_200])
    pip96.pick_up_tip(transfer_tips_200.columns()[0][0]) #grab tips with large pipette
    pip96.aspirate(75, water_magbead_mix.bottom(0.1), rate=0.5) #draw up mag bead mix slow 
    ######### 26 + sample volume? check this

    pip96.dispense(100, waste_reservoir.top()) #dispense waste
    pip96.drop_tip(waste_chute) #trash tips



    # STEP 8: Add wash buffer
    protocol.comment('STEP 8: Add wash buffer')
