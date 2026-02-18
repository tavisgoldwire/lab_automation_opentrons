from opentrons.protocol_api.labware import Labware
from opentrons import types
from opentrons.types import Point
import math
import numpy as np
from dataclasses import dataclass


metadata = {
    'protocolName': 'Zymo Magbead DNA Extraction - Modified',
    'author': 'cnguyen <calnguyen@zymoresearch.com>',
    'description': 'DNA extraction protocol using magnetic beads',
    'lastModified' : '2025-08-28'
}

requirements = {
    "robotType": "Flex",
    "apiLevel": "2.22"
}


#SET DRY RUN TRUE/FALSE IN UI


#Function to add to script UI
def add_parameters(parameters):
    parameters.add_int(
        variable_name = 'sample_count',
        display_name = 'Sample Count',
        description = 'Number of samples',
        default = 24,
        minimum = 1,
        maximum = 48
    )
    parameters.add_bool(
        variable_name = 'dry_run',
        display_name = 'Dry Run',
        description = 'Enable or disable dry-run',
        default = False
    )

@dataclass
class ReagentVolume:
    SAMPLE:                 float = 200.0
    MAGBINDING_BUFFER:      float = 600.0
    MAGBEADS:               float = 20.0
    MAGBINDING_BUFFER_WASH: float = 500.0
    MAGWASH_1:              float = 500.0
    MAGWASH_2_1:            float = 900.0
    MAGWASH_2_2:            float = 900.0
    ELUTION:                float = 75.0
    SUPERNATANT_EXT:        float = 200.0 #2nd aspiration in super removal
    AIR_GAP:                float = 20.0 #Default airgap size

    @property
    def STARTING_VOLUME(self):
        """Returns starting sample volume"""
        return self.SAMPLE
    
    @property
    def BINDING_BUFFER_VOLUME(self):
        """Returns initial value of magbeads + buffer in the reservoir"""
        return self.MAGBINDING_BUFFER + self.MAGBEADS
    
    @property
    def TOTAL_BINDING_VOLUME(self):
        """Returns total volume of beads + sample + buffer"""
        return self.MAGBINDING_BUFFER + self.MAGBEADS + self.SAMPLE

@dataclass
class Timer:
    MAGNET_SETTLING:        float = 2.0
    MAGNET_SETTLING_EXT:    float = 3.0
    WASH:                   float = 1.0
    SHAKER_WASH:            float = 1.0
    SHAKER_ELUTE:           float = 5.0
    BLINK:                  float = 1/60
    BIND:                   float = 3.0
    BEAD_DRY:               float = 10.0

@dataclass
class MixingCycle:
    PRE_MIX_MAGBEADS:       int = 3 #Repetitions to mix magbeads + binding buffer before transfer
    MIX_BINDING_SAMPLES:    int = 8 #Reps to mix sample + magbeads + binding buffer

@dataclass
class ShakerRPM:
    WASH_RPM:               int = 1200 #Shaker speed during washes
    ELUTE_RPM:              int = 800 #During elution mixing

@dataclass
class Height:
    BOTTOM_1MM:             float = 1 
    BOTTOM_0_5MM:           float = 0.5
    BOTTOM_2MM:             float = 2
    TOP_5MM:                float = -5 #Height that reagent tip dispenses at

@dataclass
class DeckLayout:
    #Module  positions
    MAGNETIC_BLOCK =    'C1'
    HEATER_SHAKER  =    'D1' #Sample plate is initially loaded on heater shaker adapter
    TEMP_MODULE    =    'A3' #Elution plate initally loaded on temp module adapter
    
    #Labware stuff
    LIQUID_WASTE   =    'C3'
    REAGENT_RES_1  =    'D2'
    REAGENT_RES_2  =    'C2'
    TRASH_BIN      =    'D3'

    #Tips
    TIPS_1000_1    =    'A2'
    TIPS_1000_2    =    'B2'
    TIPS_1000_3    =    'B3'


@dataclass
class FlowRate:
    """Flow rates in uL/s"""
    SUPER_ASPIRATION:           float = 100 #Supernatant first phase
    SUPER_DISPENSE:             float = 200
    SECOND_SUPER_ASPIRATION:    float = 50 #Supernatant second phase
    SECOND_SUPER_DISPENSE:      float = 100
    ELUTION_ASPIRATION:         float = 20 #Transfer elution solution
    ELUTION_DISPENSE:           float = 20
    MIX_ASPIRATION:             float = 250 #Speed of mixing binding buffers
    MIX_DISPENSE:               float = 250
    SLOW_MIX_ASPIRATION:        float = 150 
    SLOW_MIX_DISPENSE:          float = 150
    DEFAULT_ASPIRATION:         float = 180 #Default values
    DEFAULT_DISPENSE:           float = 180
    DEFAULT_BLOW_OUT:           float = 180

@dataclass
class LabwareType:
    RESERVOIR = "nest_12_reservoir_15ml"
    DEEPWELL = "nest_96_wellplate_2ml_deep"

@dataclass
class RunTimeParameters:
    """Used for tracking and some settings"""
    USE_GRIPPER = True
    MOUNT = 'right'
    MAX_SAMPLES = 48
    WASH_COUNT   = 1
    TIP1000     = 0
    TIP200      = 0
    DROP_COUNT  = 0
    WASTE_VOL   = 0


def run(ctx):
    #Load dataclass settings from above
    runtime = RunTimeParameters()
    reagent_volumes = ReagentVolume()
    timers = Timer()
    shaker_settings = ShakerRPM()
    mixing_settings = MixingCycle()
    deck = DeckLayout()
    labware_types = LabwareType()
    heights = Height()
    flow_rates = FlowRate()

    #Reducing all timers to 0.25 if dry-run
    if ctx.params.dry_run:
        ctx.comment(f'Dry Run enabled. Reducing all timers to 0.25.')
        for setting in timers.__dataclass_fields__:
            setattr(timers, setting, 0.25) 

    #Load trash bin
    trash = ctx.load_trash_bin(deck.TRASH_BIN)

    #Load heater shaker
    mod_heater_shaker = ctx.load_module('heaterShakerModuleV1',deck.HEATER_SHAKER)
    adap_heater_shaker = mod_heater_shaker.load_adapter('opentrons_96_deep_well_adapter')
    sample_plate = adap_heater_shaker.load_labware(labware_types.DEEPWELL,'Samples') #Sample plate initially loaded at D1 
    mod_heater_shaker.close_labware_latch()

    #Load temperature module
    temp = ctx.load_module('temperature module gen2', deck.TEMP_MODULE)
    temp_block = temp.load_adapter('opentrons_96_well_aluminum_block')
    elution_plate = temp_block.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt','Elution Plate')

    #Load magnetic block
    magblock = ctx.load_module('magneticBlockV1', deck.MAGNETIC_BLOCK)

    #Load liquid waste reservoir
    waste = ctx.load_labware('nest_1_reservoir_195ml', deck.LIQUID_WASTE,'Liquid Waste').wells()[0].top()

    #Load reagent reservoirs
    reservoir_1 = ctx.load_labware(labware_types.RESERVOIR, deck.REAGENT_RES_1, 'reagent reservoir 1')
    reservoir_2 = ctx.load_labware(labware_types.RESERVOIR, deck.REAGENT_RES_2, 'reagent reservoir 2')

    # Define reagent locations
    binding_buffer = reservoir_1.wells()[1:4] #A2 - A4
    binding_buffer_2 = reservoir_1.wells()[4:6] #A5 - A6
    wash_1 = reservoir_1.wells()[6:8] #A7 - A8
    elution_solution = reservoir_1.wells()[-1] #A12
    wash_2_1 = reservoir_2.wells()[:6] #A1 - A6
    wash_2_2 = reservoir_2.wells()[6:] #A7 - A12

    ctx.comment(f'Running with sample count: {ctx.params.sample_count}')
    # Define Sample Layout
    sample_count = ctx.params.sample_count #Pull sample count from UI or default to 24
    num_sample_columns = math.ceil(sample_count/8) #Get number of columns from sample count
    rounded_sample_count = 8 * num_sample_columns
    sample_index_columns = sample_plate.columns()[:num_sample_columns] #Get first row. Index num cols
    elution_sample_index_columns = elution_plate.columns()[:num_sample_columns]
    sample_wells = sample_plate.wells()[:(8*num_sample_columns)] 
    
    #Load tips
    tips1000 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', deck.TIPS_1000_1,'Tips 1')
    tips1001 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', deck.TIPS_1000_2,'Tips 2')
    tips1002 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', deck.TIPS_1000_3,'Tips 3')
    total_tips = [*tips1000.columns(),*tips1001.columns(),*tips1002.columns()] #Unpack list

    #Reserve Tips
    reagent_tips = total_tips[0] #Reserve first col for reagent distribution
    supernatant_tips = total_tips[1:num_sample_columns+1] #Tips for super removal
    elution_tips = total_tips[1 + num_sample_columns: 1+ 2 * num_sample_columns] #Tips for elution
    remaining_tips = total_tips[1+2*num_sample_columns:]
    runtime.TIP1000 = (len(total_tips) - len(remaining_tips)) #Calc number of reserved tips.

    # Load instruments
    m1000 = ctx.load_instrument('flex_8channel_1000', runtime.MOUNT, tip_racks=[tips1000, tips1001, tips1002])

    # Set Initial Pipette flow rates
    def reset_or_update_flow_rates(aspirate_rate=flow_rates.DEFAULT_ASPIRATION,
                                   dispense_rate=flow_rates.DEFAULT_DISPENSE,
                                   blow_out_rate=flow_rates.DEFAULT_BLOW_OUT):
        """
        Change aspiration/dispense flow rate or reset to default (call with no parameters).
        """
        m1000.flow_rate.aspirate = aspirate_rate
        m1000.flow_rate.dispense = dispense_rate
        m1000.flow_rate.blow_out = blow_out_rate

    reset_or_update_flow_rates()

    # Define liquid reagent colors
    colors = [
        '#008000','#008000','#A52A2A','#A52A2A',
        '#00FFFF','#0000FF','#800080','#ADD8E6',
        '#FF0000','#FFFF00','#FF00FF','#00008B',
        '#7FFFD4','#FFC0CB','#FFA500','#00FF00',
        '#C0C0C0',"#6D2696"
        ]

    locations = [
        binding_buffer,
        binding_buffer_2,
        wash_1,
        wash_2_1,
        wash_2_2,
        elution_solution
        ]
    
    vols = [
        reagent_volumes.BINDING_BUFFER_VOLUME,
        reagent_volumes.MAGBINDING_BUFFER_WASH,
        reagent_volumes.MAGWASH_1,
        reagent_volumes.MAGWASH_2_1,
        reagent_volumes.MAGWASH_2_2,
        reagent_volumes.ELUTION
    ]

    liquids = [
        'MagBinding Buffer With Beads',
        'MagBinding Buffer Wash',
        'MagWash 1',
        'MagWash 2-1',
        'MagWash 2-2',
        'DNase/RNase Free Water'
        ]

    # Define liquids
    sample_liquid = ctx.define_liquid(name='Samples',description='Samples',display_color='#C0C0C0')
    
    for sample in sample_wells: #Sample wells is defined as individual wells on sample plate.
        sample.load_liquid(liquid=sample_liquid, volume=reagent_volumes.SAMPLE)

    if len(colors) > len(liquids): #Truncate colors list due to zip used later.
        colors = colors[:len(liquids)]

    def liquids_(liquid_name, location, color, vol):
        # TODO Re-write this function 
        sampnum = rounded_sample_count
        
        if liquid_name == "MagBinding Buffer With Beads":
            extra_samples = math.ceil(1500/reagent_volumes.BINDING_BUFFER_VOLUME)
        else:
            extra_samples = math.ceil(1500/vol)
        
        if isinstance(location,list):
            limit = runtime.MAX_SAMPLES/len(location)
            iterations = math.ceil(sampnum/limit)
            left = sampnum - limit
            while left>limit:
                left = left - limit
            if left > 0:
                last_iteration_samp_num = left
            elif left < 0:
                last_iteration_samp_num = sampnum
            else:
                last_iteration_samp_num = limit

            samples_per_well = []
            for i in range(iterations):
                if i == (iterations-1):
                    samples_per_well.append(last_iteration_samp_num)
                else:
                    samples_per_well.append(limit)

            liquid_name = ctx.define_liquid(name=str(liquid_name),description=str(liquid_name),display_color=color)
            for sample, well in zip(samples_per_well,location[:len(samples_per_well)]):
                v = vol*(sample+extra_samples)
                well.load_liquid(liquid=liquid_name,volume=v)
        else:
            v = vol*(sampnum+extra_samples)
            liquid_name = ctx.define_liquid(name=str(liquid_name),description=str(liquid_name),display_color=color)
            location.load_liquid(liquid=liquid_name,volume=v)

    # Generate liquids
    for (ll,l,c,v) in zip(liquids,locations,colors,vols):
        liquids_(ll,l,c,v)

    def transport(initial_position: Labware, final_position, use_gripper=runtime.USE_GRIPPER, drop_offset=None):
        """
        Submethod - Plate movement on deck - Global Process
        """
        if drop_offset:
            ctx.move_labware(initial_position, final_position, use_gripper=use_gripper, drop_offset=drop_offset)
        else:
            ctx.move_labware(initial_position, final_position, use_gripper=use_gripper)

    def aspirate_and_dispense(volume, source, destination, air_gap=reagent_volumes.AIR_GAP, blow_out=False):
        """Similar to transfer function but enabling future features"""
        m1000.aspirate(volume, source)
        m1000.air_gap(air_gap)
        m1000.dispense(volume + air_gap, destination)

        if blow_out:
            m1000.blow_out(destination)

    def track_waste(volume: float):
        """Track volume contained in waste"""
        runtime.WASTE_VOL += (volume*8)
        if runtime.WASTE_VOL >= 185000:
            m1000.home()
            blink()
            ctx.pause('Please empty liquid waste before resuming.')
            runtime.WASTE_VOL = 0

    def get_tips():
        """Retrieve non-reserved tips"""
        m1000.pick_up_tip(total_tips[int(runtime.TIP1000)][0])
        runtime.TIP1000 += 1

    def return_tips():
        m1000.return_tip()

    def drop_tips():
        """Used to track"""

        m1000.drop_tip()
        runtime.DROP_COUNT += 1
        if runtime.DROP_COUNT >= 18: #18 x 8 = num of pipettes that waste bin can store
            runtime.DROP_COUNT = 0
            ctx.pause("Please empty the waste bin before continuing.")

    def move_to_magnet(source_plate: Labware, duration: float = 0):
        transport(source_plate, magblock, drop_offset={"x": 0, "y": 0, "z": -1})
        if duration > 0:
            for timer in np.arange(duration, -0.5): # Settling time delay with countdown timer
                        ctx.delay(minutes=0.5, msg=f"Incubating on magnetic block – {timer} minutes remaining.")

    def shake_mix(source_plate: Labware, 
                    shake_speed: int=500, 
                    duration: float=1, 
                    adapter=adap_heater_shaker,
                    move_to=False):
            """
            Mix plate via heater shaker 

            Args:
                plate(labware): plate to mix
                shake_speed(int): RPM
                duration(float): Time in minutes
                adapater: Adapter placed on heater-shaker
                move_to: Transport plate or not.
            """

            if move_to:
                mod_heater_shaker.open_labware_latch()
                transport(source_plate, adapter)
            mod_heater_shaker.close_labware_latch() #Confirm closed
            mod_heater_shaker.set_and_wait_for_shake_speed(shake_speed)
            
            for timer in np.arange(duration,-0.5): # Settling time delay with countdown timer
                        ctx.delay(minutes=0.5, msg= f'There are {timer} minutes left in the mixing process.')

            mod_heater_shaker.deactivate_shaker()
            mod_heater_shaker.open_labware_latch()

    def blink():
        ctx.comment("Blinking")
        for _ in range(3):
            ctx.set_rail_lights(True)
            ctx.delay(minutes=timers.BLINK)
            ctx.set_rail_lights(False)
            ctx.delay(minutes=timers.BLINK)

    def remove_supernatant(volume: float, dispose_tips=False):
        ctx.comment("Removing Supernatant")
        track_waste(volume) #Prevent overflow

        for super_tips, sample_col in zip(supernatant_tips, sample_index_columns):
            m1000.pick_up_tip(super_tips[0]) #Get super tips

            reset_or_update_flow_rates(aspirate_rate=flow_rates.SUPER_ASPIRATION,
                            dispense_rate=flow_rates.SUPER_DISPENSE)

            aspirate_and_dispense(volume=volume,
                                  source=sample_col[0].bottom(heights.BOTTOM_1MM),
                                  destination=waste,
                                  air_gap=reagent_volumes.AIR_GAP)
            
            reset_or_update_flow_rates(aspirate_rate=flow_rates.SECOND_SUPER_ASPIRATION,
                dispense_rate=flow_rates.SECOND_SUPER_DISPENSE)
            
            aspirate_and_dispense(volume=reagent_volumes.SUPERNATANT_EXT,
                                  source=sample_col[0].bottom(heights.BOTTOM_0_5MM),
                                  destination=waste,
                                  air_gap=reagent_volumes.AIR_GAP,
                                  blow_out=True)

            if dispose_tips:
                drop_tips()
            else:
                return_tips()

        reset_or_update_flow_rates()

    def smart_mix(source, volume: float, large_volume_mix: bool = False, reps: int=5, mix_ratio: float=0.8):
        """
        Submethod - Resuspend Mix - Global Process
        Args:
        source_plate
        volume(float)
        large_volume_mix(bool) True if mixing large volumes
        reps(int) Number of times to repeat mixing cycle
        mix-ratio(float) Ratio of volume to use in mixing
        """
        mixing_volume = volume * mix_ratio

        if large_volume_mix:
            reset_or_update_flow_rates(aspirate_rate=flow_rates.MIX_ASPIRATION, dispense_rate=flow_rates.MIX_DISPENSE)
            #Large volume positions
            mix_positions = [source.bottom().move(types.Point(z=z)) for z in [1, 8, 16, 24]]
            
        else:
            reset_or_update_flow_rates(aspirate_rate=flow_rates.SLOW_MIX_ASPIRATION, dispense_rate=flow_rates.SLOW_MIX_DISPENSE)
            #Small volume positions
            mix_positions = [source.bottom().move(types.Point(z=z)) for z in [0.1, 0.5, 1]]

        num_locations = len(mix_positions)

        for rep in range(reps):
            for loc_index in range(num_locations):
                #Always aspirates from lowest position
                aspirate_and_dispense(volume = mixing_volume,
                                      source = mix_positions[0],
                                      destination = mix_positions[loc_index],
                                      air_gap=0)

        reset_or_update_flow_rates(aspirate_rate=flow_rates.SLOW_MIX_ASPIRATION, dispense_rate=flow_rates.SLOW_MIX_DISPENSE)

        #Additional slow mix
        aspirate_and_dispense(volume = mixing_volume,
                        source = mix_positions[0],
                        destination=mix_positions[0],
                        air_gap=0)

        reset_or_update_flow_rates()

    def wash(source_plate, volume, dispose_tips=False):
        """Wash steps 
        Dispose_tips: trash tips after final use."""
        ctx.comment(f"Starting wash #{RunTimeParameters.WASH_COUNT}")
        RunTimeParameters.WASH_COUNT += 1
        num_res_wells = len(source_plate)
        max_sample_columns = int(runtime.MAX_SAMPLES / 8)
        uses_per_res_well = max_sample_columns // num_res_wells
        m1000.pick_up_tip(reagent_tips[0])

        reset_or_update_flow_rates(aspirate_rate=150, dispense_rate=200)

        for index, sample_well in enumerate(sample_index_columns):
            source = source_plate[index//uses_per_res_well]
            
            aspirate_and_dispense(source=source.bottom(heights.BOTTOM_2MM),
                                  destination=sample_well[0].top(heights.TOP_5MM),
                                  volume=volume)
        return_tips()

        shake_mix(source_plate=sample_plate,
                  shake_speed=shaker_settings.WASH_RPM,
                  duration=timers.SHAKER_WASH,
                  move_to=True)
        
        move_to_magnet(source_plate=sample_plate, duration=timers.MAGNET_SETTLING)

        remove_supernatant(volume=volume, dispose_tips=dispose_tips)


    def bind():
        ctx.comment('Beginning Binding Step')

        m1000.pick_up_tip(reagent_tips[0])
        for index, sample_well in enumerate(sample_index_columns):
            source = binding_buffer[index//2]
            smart_mix(source=source,
                      volume=reagent_volumes.BINDING_BUFFER_VOLUME,
                      large_volume_mix=True,
                      reps=mixing_settings.PRE_MIX_MAGBEADS)
            
            aspirate_and_dispense(source=source.bottom(heights.BOTTOM_2MM),
                                  destination=sample_well[0].top(heights.TOP_5MM),
                                  volume=reagent_volumes.BINDING_BUFFER_VOLUME)
        return_tips()
            
        for super_tips, sample_col in zip(supernatant_tips, sample_index_columns):
            m1000.pick_up_tip(super_tips[0]) #Get super tips

            smart_mix(source=sample_col[0],
                      volume=reagent_volumes.TOTAL_BINDING_VOLUME,
                      reps = mixing_settings.MIX_BINDING_SAMPLES)

            return_tips()

        reset_or_update_flow_rates()
            
        for timer in np.arange(timers.BIND,-0.5): # Settling time delay with countdown timer
            ctx.delay(minutes=0.5, msg= f'There are {timer} minutes left in the binding process.')
        
        mod_heater_shaker.open_labware_latch() #ensure open
        move_to_magnet(sample_plate, timers.MAGNET_SETTLING_EXT)
        remove_supernatant(reagent_volumes.TOTAL_BINDING_VOLUME)

    def elute():
        mod_heater_shaker.set_and_wait_for_temperature(55)
        mod_heater_shaker.open_labware_latch()
        transport(sample_plate, adap_heater_shaker)
        mod_heater_shaker.close_labware_latch() #Confirm closed
            
        for timer in np.arange(timers.BEAD_DRY,-0.5): # Settling time delay with countdown timer
                    ctx.delay(minutes=0.5, msg= f'There are {timer} minutes left in the drying process.')

        reset_or_update_flow_rates(aspirate_rate=flow_rates.ELUTION_ASPIRATION, dispense_rate=flow_rates.ELUTION_DISPENSE)

        for elute_tips, sample_col in zip(elution_tips, sample_index_columns):
            m1000.pick_up_tip(elute_tips[0]) #Get super tips

            aspirate_and_dispense(source=elution_solution.bottom(heights.BOTTOM_1MM),
                                  destination=sample_col[0].bottom(heights.BOTTOM_2MM),
                                  volume=reagent_volumes.ELUTION,
                                  air_gap=0)

            return_tips()

        shake_mix(source_plate=sample_plate,
                  shake_speed=shaker_settings.ELUTE_RPM,
                  duration=timers.SHAKER_ELUTE,
                  move_to=False)
        
        move_to_magnet(sample_plate, timers.MAGNET_SETTLING)


        for elute_tips, sample_col, elute_col in zip(elution_tips, sample_index_columns, elution_sample_index_columns):
            m1000.pick_up_tip(elute_tips[0]) #Get super tips

            aspirate_and_dispense(source=sample_col[0].bottom(heights.BOTTOM_0_5MM),
                                  destination=elute_col[0].bottom(heights.BOTTOM_1MM),
                                  volume=reagent_volumes.ELUTION,
                                  air_gap=0)

            drop_tips()

        mod_heater_shaker.deactivate_heater()
        mod_heater_shaker.open_labware_latch



    
    """
    Here is where you can call the methods defined above to fit your specific
    protocol. The normal sequence is:
    """


    bind()
    wash(binding_buffer_2, reagent_volumes.MAGBINDING_BUFFER_WASH)
    wash(wash_1, reagent_volumes.MAGWASH_1)
    wash(wash_2_1, reagent_volumes.MAGWASH_2_1)
    wash(wash_2_2, reagent_volumes.MAGWASH_2_2, dispose_tips=True) #Dump supernatant tips after final use.
    elute()
