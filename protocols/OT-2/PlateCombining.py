from opentrons import protocol_api
import math

metadata = {
    'protocolName': 'Plate Combining',
    'author': 'OpentronsAI',
    'description': 'Move samples from source to destination plates',
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="plate_combine_data",
        display_name="Plate Combining CSV",
        description="CSV with source_plate, source_well, dest_plate, dest_well, volume"
    )
    
    parameters.add_int(
        variable_name="num_source_plates",
        display_name="Number of Source Plates",
        description="How many source plates to use (1-5)",
        default=3,
        minimum=1,
        maximum=5
    )
    
    parameters.add_int(
        variable_name="num_destination_plates",
        display_name="Number of Destination Plates",
        description="How many destination plates to use (1-3)",
        default=2,
        minimum=1,
        maximum=3
    )

def run(protocol: protocol_api.ProtocolContext):
    # Access runtime parameters
    num_source_plates = protocol.params.num_source_plates
    num_destination_plates = protocol.params.num_destination_plates
    
    # Parse CSV data
    csv_data = protocol.params.plate_combine_data.parse_as_csv()
    csv_rows = list(csv_data)
    headers = csv_rows[0]
    
    # Process CSV and create data structure
    well_data = []
    for row in csv_rows[1:]:
        try:
            well_data.append({
                'source_plate': int(float(row[0])),
                'source_well': str(row[1]).strip(),
                'dest_plate': int(float(row[2])),
                'dest_well': str(row[3]).strip(),
                'volume': float(row[4])
            })
        except (ValueError, IndexError) as e:
            protocol.comment(f"Error parsing row: {row}")
            raise ValueError(f"CSV parsing error: {str(e)}")

    protocol.comment(f"Successfully parsed {len(well_data)} rows from CSV")

    # ============================================================================
    # VALIDATION SECTION
    # ============================================================================
    protocol.comment("=" * 60)
    protocol.comment("VALIDATION: Checking CSV data against loaded plates")
    protocol.comment("=" * 60)
    
    validation_errors = []
    required_source_plates = set()
    required_destination_plates = set()
    
    # Validate each row
    for row_number, row in enumerate(well_data, start=2):
        # Validate volumes
        if row['volume'] <= 0:
            validation_errors.append(f"Row {row_number}: Sample volume must be > 0")
        
        # Track required plates
        required_source_plates.add(row['source_plate'])
        required_destination_plates.add(row['dest_plate'])
        
        # Validate plate numbers
        if row['source_plate'] < 1 or row['source_plate'] > num_source_plates:
            validation_errors.append(
                f"Row {row_number}: Source plate {row['source_plate']} not loaded"
            )
        
        if row['dest_plate'] < 1 or row['dest_plate'] > num_destination_plates:
            validation_errors.append(
                f"Row {row_number}: Destination plate {row['dest_plate']} not loaded"
            )
    
    # Display validation summary
    protocol.comment("-" * 60)
    protocol.comment(f"Source plates required: {sorted(required_source_plates)}")
    protocol.comment(f"Destination plates required: {sorted(required_destination_plates)}")
    protocol.comment("-" * 60)
    
    if validation_errors:
        protocol.comment("VALIDATION FAILED:")
        for error in validation_errors:
            protocol.comment(error)
        raise ValueError(f"CSV validation failed with {len(validation_errors)} error(s)")
    
    # ============================================================================
    # DEFINE LIQUIDS FOR DECK VISUALIZATION
    # ============================================================================
    
    # Define liquid types with distinct colors for easy identification
    source_liquid = protocol.define_liquid(
        name="Source Samples",
        description="Samples to be transferred from source plates",
        display_color="#00FF00"  # Green
    )
    
    destination_liquid = protocol.define_liquid(
        name="Destination Wells",
        description="Wells receiving transferred samples",
        display_color="#0000FF"  # Blue
    )
        
    # ============================================================================
    # LABWARE LOADING
    # ============================================================================
    
    # Load source plates
    source_plates = {}
    source_slots = [4, 5, 6, 7, 8]
    for i in range(num_source_plates):
        plate_num = i + 1
        source_plates[plate_num] = protocol.load_labware(
            'opentrons_96_wellplate_200ul_pcr_full_skirt',
            source_slots[i],
            f'Source Plate {plate_num}'
        )
    
    # Load destination plates
    destination_plates = {}
    destination_slots = [1, 2, 3]
    for i in range(num_destination_plates):
        plate_num = i + 1
        destination_plates[plate_num] = protocol.load_labware(
            'opentrons_96_wellplate_200ul_pcr_full_skirt',
            destination_slots[i],
            f'Destination Plate {plate_num}'
        )
    
    # Load tip racks
    tips_20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 10, 'Tips Rack 1')
    tips_20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 11, 'Tips Rack 2')
    
    # Load pipette
    p20_single = protocol.load_instrument(
        'p20_single_gen2', 
        'right', 
        tip_racks=[tips_20_1, tips_20_2]
    )

    # ============================================================================
    # LOAD LIQUIDS INTO WELLS FOR VISUALIZATION
    # ============================================================================
    
    # Track which wells have been marked to avoid duplicates
    marked_source_wells = {}
    marked_dest_wells = {}
    
    for row in well_data:
        # Mark source wells with liquid
        plate_num = row['source_plate']
        well_name = row['source_well']
        key = (plate_num, well_name)
        
        if key not in marked_source_wells:
            source_plates[plate_num][well_name].load_liquid(
                liquid=source_liquid,
                volume=100  # Placeholder volume for visualization
            )
            marked_source_wells[key] = True
        
        # Mark destination wells with liquid
        dest_plate_num = row['dest_plate']
        dest_well_name = row['dest_well']
        dest_key = (dest_plate_num, dest_well_name)
        
        if dest_key not in marked_dest_wells:
            destination_plates[dest_plate_num][dest_well_name].load_liquid(
                liquid=destination_liquid,
                volume=0  # Empty initially
            )
            marked_dest_wells[dest_key] = True

    protocol.comment("=" * 60)
    protocol.comment("DECK SETUP COMPLETE - Check app for plate positions")
    protocol.comment("=" * 60)
    protocol.comment(f"Source plates in slots: {[source_slots[i] for i in range(num_source_plates)]}")
    protocol.comment(f"Destination plates in slots: {[destination_slots[i] for i in range(num_destination_plates)]}")
    protocol.comment(f"Tip racks in slots: 10, 11")
    protocol.comment("=" * 60)
    protocol.comment("STARTING PROTOCOL")
    protocol.comment("=" * 60)

    # ============================================================================
    # Transfer samples between plates
    # ============================================================================
    for row in well_data:
        source_plate = source_plates[row['source_plate']]
        destination_plate = destination_plates[row['dest_plate']]
        source_well = source_plate[row['source_well']]
        dest_well = destination_plate[row['dest_well']]
        sample_vol = row['volume']

        # Pick up tip before aspirating
        p20_single.pick_up_tip()
        # Pipette mix (in case the volume is off, don't leave all DNA at bottom)
        if sample_vol > 20:
            mixing_vol = 20
        else:
            mixing_vol = .8 * sample_vol

        p20_single.aspirate(mixing_vol, source_well.bottom(z=0.5))
        p20_single.dispense(mixing_vol, source_well.bottom(z=0.5))
        p20_single.aspirate(mixing_vol, source_well.bottom(z=0.5))
        p20_single.dispense(mixing_vol, source_well.bottom(z=0.5))
        p20_single.aspirate(mixing_vol, source_well.bottom(z=0.5))
        p20_single.dispense(mixing_vol, source_well.bottom(z=0.5))

        # Split sample transfer if needed
        if sample_vol > 19:
            num_transfers = math.ceil(sample_vol / 19)
            for i in range(num_transfers):
                if i == num_transfers - 1:
                    transfer_vol = sample_vol - (i * 19)
                else:
                    transfer_vol = 19
                    
                p20_single.aspirate(transfer_vol, source_well.bottom(z=0.5))
                if transfer_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(transfer_vol + 0.5, dest_well.bottom(z=1))
                else:
                    p20_single.dispense(transfer_vol, dest_well.bottom(z=1))
                    
                p20_single.blow_out(dest_well.bottom(z=2))
                p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                p20_single.blow_out(dest_well.top(z=-2))
        else:
            p20_single.aspirate(sample_vol, source_well.bottom(z=0.5))
            if sample_vol >= 0.5:
                p20_single.air_gap(0.5)
                p20_single.dispense(sample_vol + 0.5, dest_well.bottom(z=1))
            else:
                p20_single.dispense(sample_vol, dest_well.bottom(z=1))
            p20_single.blow_out(dest_well.bottom(z=2))
            p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
            p20_single.blow_out(dest_well.top(z=-2))
        
        # Drop tip after completing transfer        
        p20_single.drop_tip()

    # ============================================================================
    # PROTOCOL COMPLETE
    # ============================================================================
    protocol.comment("=" * 60)
    protocol.comment("PROTOCOL COMPLETE!")
    protocol.comment("=" * 60)
