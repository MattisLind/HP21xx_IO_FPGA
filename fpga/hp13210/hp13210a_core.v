// Ported from hp2116_verilog/hp13210a.sv at f07b9637157b990d54c7959e7d8c0b1c27f18a61.
// Verilog-2001 / ISE 14.7. Logical bus levels, not physical HP connector levels.
// See README.md for intentional reset and FSMC read-mux changes.
`timescale 1ns/1ps

module hp13210a_core #(parameter [3:0] RESET_NOT_READY = 4'hf) (
  input wire         clk,
  input wire         reset,
  input wire         crs,

  // Priority and flag chain toward the backplane.
  output reg         prl,
  output reg         flgl,
  input wire         sfc,
  output reg         irql,
  input wire         clf,
  input wire         ien,
  input wire         stf,
  input wire         iak,
  input wire         t3,
  output reg         skf,

  // Select code for the lower address half. These are used by the interface.
  input wire         scm_l,
  input wire         scl_l,

  input wire         iog,
  input wire         popio,

  // Special signal from the bus sheet. Not used in this first model.
  input wire         iob16_or_bios_n,

  output reg         srq,
  input wire         ioo,
  input wire         clc,
  input wire         stc,
  input wire         prh,
  input wire         ioi,
  input wire         sfs,

  // Higher select code selects the command channel.
  output reg         irqh,
  input wire         scl_h,
  input wire         scm_h,

  input wire [15:0]  iob_out,
  output reg [15:0]  iob_in,

  input wire         sir,
  input wire         enf,
  output reg         flgh,

  input wire         run,

  input wire         edt,
  input wire         pon,
  input wire         bioo_n,
  input wire         sfsb_or_bioi_n,
  input wire         stm32_fsmc_ne,
  input wire         stm32_fsmc_nadv,
  input wire         stm32_fsmc_nwe,
  input wire         stm32_fsmc_noe,
  input  wire   [15:0] stm32_fsmc_ad_in,
  output reg    [15:0] stm32_fsmc_ad_out,
  output wire         stm32_fsmc_ad_oe,
  output reg         stm32_irq, 
  output reg         stm32_drq
);

localparam [2:0] SEEK_IDLE = 3'd0,
  SEEK_GOT_SEEK_CMD = 3'd1,
  SEEK_STORED_DATA = 3'd2,
  SEEK_GET_NEXT_WORD = 3'd3,
  SEEK_GOT_SECOND_WORD = 3'd4;

  reg [2:0] seek_state;

  //--------------------------------------------------------------------------
  // Selection / decoded local strobes
  //--------------------------------------------------------------------------
  reg dsel,csel;


  //--------------------------------------------------------------------------
  // Internal state
  //--------------------------------------------------------------------------
  reg        data_channel_flag_ff;
  reg        data_channel_flag_buffer_ff;
  reg        command_channel_flag_ff;
  reg        command_channel_flag_buffer_ff;  
  reg        command_channel_control_ff;
  reg        data_channel_encode_ff;
  reg        read_dma_ended;
  reg        discard_read_stc;
  reg        command_channel_encode_ff;
  reg        irq_ff;
  reg        [1:0] drive_select_register; 
  reg        protected_cylinder_register;
  reg        defective_cylinder_register;
  reg [3:0]  first_status, overrun, drive_unsafe, data_protect, seek_check, not_ready, end_of_cylinder, address_error;
  reg [3:0]  flagged_cylinder, drive_busy, data_error;
  reg any_error;
  reg [3:0]  seeking , seek_aborted ;
  // OTA changes the selected drive on this same edge. Decode its incoming
  // word when deciding which pending seek is affected by the new command.
  wire [1:0] seek_abort_drive = (ioo & csel) ? iob_out[1:0] : drive_select_register;
  wire seek_abort_is_status = (ioo & csel) ? (iob_out[15:12] == 4'h0) : command_is_status_check;
  reg        [3:0] attention_input_register;
  reg        data_op;
  reg        drv0_sel, drv1_sel, drv2_sel, drv3_sel;
  reg        [3:0] address_register;   // internal address register used by the micro controller to access internal registers.
  reg        [15:0] data_interface_output_buffer_register; // data going from host to drive
  reg        [15:0] data_interface_input_buffer_register; // data going from drive to host
  reg        cmd_status, cmd_cd;
  reg        eow, sk_set_dflag, gate_status;
  reg        [3:0] command_register;
  reg        hp7900_data_n_status;
  reg        stm32_data_access;
  reg        stm32_status_access;
  reg        stm32_read_csr;
  reg [1:0] csr_read_flags;
  reg        stm32_write_csr;
  // Drives accept seeks independently; retain one destination per drive until
  // the MCU takes it. Ordinary controller operations use one separate slot.
  reg [14:0] seek_addresses [0:3];
  reg [3:0] seek_pending;
  reg command_pending;
  reg [15:0] pending_command;
  reg [14:0] pending_address;
  reg seek_was_busy;
  wire [1:0] pending_drive = seek_pending[0] ? 2'd0 :
      seek_pending[1] ? 2'd1 : seek_pending[2] ? 2'd2 : 2'd3;
  wire pending_seek = |seek_pending;
  reg [15:0] captured_command, captured_address;
  reg captured_request_valid;
  reg seek_request_delayed, seek_record_read_delayed;
  wire stm32_irq_ff = pending_seek | command_pending;
  reg        stm32_data_channel_irq_ff;
  reg        stm32_data_channel_irq_enable;
  reg        stm32_7900_command_status_access;
  reg        stm32_read_7900_command_status;
  reg        stm32_write_7900_command_status;
  reg        stm32_write_7900_command_status_delayed;
  reg        stm32_write_7900_command_status_negedge;
  reg        stm32_write_7900_command_status_registered;
  reg        stm32_7900_data_access;
  reg        stm32_read_7900_data;
  reg        stm32_read_7900_data_registered;
  reg        stm32_read_7900_data_delayed;
  reg        stm32_read_7900_data_negedge;
  reg        stm32_write_7900_data;
  reg        stm32_write_7900_data_registered;
  reg        stm32_write_7900_data_delayed;
  reg        stm32_write_7900_data_negedge;
  reg        stm32_7900_seek_record_access;
  reg        stm32_read_7900_seek_record;
  reg        stm32_irq_enable;
  reg        set_data_channel_flag_buffer;
  reg        command_channel_control_ff_delayed;
  reg        stm32_write_7900_attention;
  reg        stm32_read_7900_attention;
  reg        stm32_7900_attention_access;
  reg        stm32_write_7900_attention_delayed;
  reg        stm32_write_7900_attention_negedge;
  reg        stm32_write_7900_attention_registered;
  reg        stm32_read_csr_negedge;
  reg        stm32_read_csr_delayed;
  reg        stm32_read_csr_registered;
  reg        stc_data_channel; 
  reg        stc_data_channel_delayed;
  reg        stc_data_channel_negedge;
  reg        stc_data_channel_posedge;
  reg        seek_record_command;
  reg        seek_or_address_record_command;
  reg        status_check_command;
  reg        stm32_7900_command_set_status_access;
  reg        stm32_7900_command_clear_status_access;
  reg        stm32_7900_command_set_status;
  reg        stm32_7900_command_clear_status;

  reg        command_is_status_check;
  reg        command_is_write_data;
  reg        command_is_read_data;
  reg        command_is_seek_record;
  reg        command_is_refine_sector;
  reg        command_is_check_data;
  wire late_read_request = read_dma_ended && command_is_read_data &&
       command_channel_control_ff && !command_channel_flag_ff &&
       !command_channel_flag_buffer_ff;
  reg        command_is_initalize_data;
  reg        command_is_address_record;
  reg        command_is_seek_record_or_address_record;
  reg        command_channel_control_ff_posedge;

  reg [7:0]  cylinder_address;
  reg [1:0]  head_address;
  reg [4:0]  sector_address;
  reg        reset_data_channel_encode_ff;
  reg        set_irq_ff;
  wire backend_request = (command_is_seek_record & set_irq_ff & ~seek_request_delayed) |
       ((command_is_write_data | command_is_read_data | command_is_refine_sector |
         command_is_check_data | command_is_initalize_data) & command_channel_control_ff_posedge);
  // Take the packet and latch the returned IRQ bits at the same read-start
  // edge. CLC or a new request during the read cannot change its identity.
  wire csr_read_start = stm32_read_csr & ~stm32_read_csr_registered;
  wire request_pop = csr_read_start & stm32_irq_ff;

  localparam [3:0] STM32_REG_CSR                     = 4'h0;
  localparam [3:0] STM32_REG_7900_COMMAND_STATUS     = 4'h2;
  localparam [3:0] STM32_REG_7900_DATA               = 4'h4;
  localparam [3:0] STM32_REG_7900_ATTENTION          = 4'h6;
  localparam [3:0] STM32_REG_7900_SET_STATUS         = 4'h8;
  localparam [3:0] STM32_REG_7900_CLEAR_STATUS       = 4'hA;
  localparam [3:0] STM32_REG_7900_SEEK_RECORD        = 4'hC;
  localparam [3:0] STM32_REG_TEST = 4'hE;
  reg [15:0] test_register;

  // Multiplexed address bits may remain on AD after NADV rises while NWE
  // is already low. Keep the last data-phase sample and commit once per
  // address transaction after synchronized NWE stays high for two samples.
  // A brief release at the address/data boundary must not commit the address.
  // AD transitions can couple a one-sample low pulse onto NADV. Only a
  // stable address phase may latch AD or rearm the write transaction.
  reg fsmc_address_window_delayed;
  wire fsmc_address_window = !stm32_fsmc_ne && !stm32_fsmc_nadv;
  wire fsmc_address_valid = fsmc_address_window && fsmc_address_window_delayed;
  always @(posedge clk) begin
    if (reset || popio) fsmc_address_window_delayed <= 1'b0;
    else fsmc_address_window_delayed <= fsmc_address_window;
  end

  reg fsmc_write_active;
  reg fsmc_write_done;
  reg fsmc_nwe_high_delayed;
  reg [15:0] fsmc_write_data;
  reg [3:0] fsmc_write_address;
  wire fsmc_write_window = !stm32_fsmc_ne && stm32_fsmc_nadv &&
                           !stm32_fsmc_nwe && stm32_fsmc_noe;
  // Multiplexed FSMC has a short NWE release at the address/data boundary.
  // It must stay high for two samples before this is a completed write.
  wire fsmc_write_commit = fsmc_write_active && stm32_fsmc_nwe &&
                          fsmc_nwe_high_delayed && !fsmc_write_done &&
                          stm32_fsmc_nadv && !stm32_fsmc_ne;
  always @(posedge clk) begin
    if (reset || popio) begin
      fsmc_write_active <= 1'b0;
      fsmc_write_done <= 1'b0;
      fsmc_nwe_high_delayed <= 1'b0;
      fsmc_write_data <= 16'h0000;
      fsmc_write_address <= 4'h0;
    end else begin
      fsmc_nwe_high_delayed <= stm32_fsmc_nwe;
      if (fsmc_address_valid) begin
        fsmc_write_active <= 1'b0;
        fsmc_write_done <= 1'b0;
      end else if (fsmc_write_commit) begin
        fsmc_write_active <= 1'b0;
        fsmc_write_done <= 1'b1;
      end else if (fsmc_write_window && !fsmc_write_done) begin
        fsmc_write_active <= 1'b1;
        fsmc_write_data <= stm32_fsmc_ad_in;
        fsmc_write_address <= address_register;
      end
    end
  end

  // NOE can pulse low during a write on the physical multiplexed bus.
  // Only a stable read window may acknowledge requests or present HP data.
  reg fsmc_read_window_delayed;
  wire fsmc_read_window = !stm32_fsmc_ne && stm32_fsmc_nadv &&
                          !stm32_fsmc_noe && stm32_fsmc_nwe;
  wire fsmc_read_valid = fsmc_read_window && fsmc_read_window_delayed;
  always @(posedge clk) begin
    if (reset || popio) fsmc_read_window_delayed <= 1'b0;
    else fsmc_read_window_delayed <= fsmc_read_window;
  end

  //localparam [3:0] STM32_REG_DATA       = 4'hc;
  //localparam [3:0] STM32_REG_IRQ_STATUS = 4'he;

  //--------------------------------------------------------------------------
  // Backplane outputs
  //--------------------------------------------------------------------------
  always @* begin

    //strobe_attention 
    data_op = 1'b1; 
    any_error = data_error[drive_select_register] | seek_check[drive_select_register] | drive_busy[drive_select_register] | address_error[drive_select_register] | drive_unsafe[drive_select_register] | overrun[drive_select_register] | end_of_cylinder[drive_select_register] | drive_busy[drive_select_register] | first_status[drive_select_register];

    dsel  = iog && scm_l && scl_l;
    csel  = iog && scm_h && scl_h;

    // Preserve reference routing: command IRQ uses the higher channel.
    flgl = 1'b0;
    flgh = irq_ff;
    irqh = irq_ff;
    prl = prh & ~(command_channel_flag_ff & ien & command_channel_control_ff);
    irql = 1'b0;
    srq = data_channel_flag_ff;
    eow = 1'b1;
    sk_set_dflag = 1'b0;
    gate_status = 1'b0;

    // The skip line is driven only when the card is selected.
    skf  = (data_channel_flag_ff & sfs & dsel) | (~data_channel_flag_ff & sfc & dsel) | (command_channel_flag_ff & sfs & csel) | (~command_channel_flag_ff & sfc & csel);

    
    if (dsel & ioi) iob_in [15:0] = data_interface_input_buffer_register;
    else iob_in = 16'h0000;


    if (ioi & csel) iob_in [15:0] = {12'b000000000000, attention_input_register};

    drv0_sel = ~drive_select_register[0] & ~drive_select_register[1];
    drv1_sel = ~drive_select_register[0] & drive_select_register[1];
    drv2_sel = drive_select_register[0] & ~drive_select_register[1];
    drv3_sel = drive_select_register[0] & drive_select_register[1];

    stm32_data_access = stm32_fsmc_nadv & ~stm32_fsmc_ne;

    stm32_status_access = stm32_data_access & (address_register == STM32_REG_CSR);
    stm32_read_csr = fsmc_read_valid & stm32_status_access;
    stm32_write_csr = fsmc_write_commit && fsmc_write_address == STM32_REG_CSR;

    stm32_read_csr_negedge = ~stm32_read_csr_registered & stm32_read_csr_delayed;

    stm32_7900_command_status_access = stm32_data_access & (address_register == STM32_REG_7900_COMMAND_STATUS);
    stm32_read_7900_command_status = stm32_7900_command_status_access & fsmc_read_valid;
    stm32_write_7900_command_status = fsmc_write_commit && fsmc_write_address == STM32_REG_7900_COMMAND_STATUS;
    
    stm32_write_7900_command_status_negedge = ~stm32_write_7900_command_status_registered & stm32_write_7900_command_status_delayed;

 
    stm32_7900_data_access = stm32_data_access & (address_register == STM32_REG_7900_DATA);
    stm32_read_7900_data = stm32_7900_data_access & fsmc_read_valid;
    stm32_write_7900_data = fsmc_write_commit && fsmc_write_address == STM32_REG_7900_DATA;


    stm32_write_7900_data_negedge = ~stm32_write_7900_data_registered & stm32_write_7900_data_delayed;
    stm32_read_7900_data_negedge = ~stm32_read_7900_data_registered & stm32_read_7900_data_delayed;

    stm32_7900_attention_access = stm32_data_access & (address_register == STM32_REG_7900_ATTENTION);
    stm32_read_7900_attention = stm32_7900_attention_access & fsmc_read_valid;
    stm32_write_7900_attention = fsmc_write_commit && fsmc_write_address == STM32_REG_7900_ATTENTION;

    stm32_write_7900_attention_negedge = ~stm32_write_7900_attention_registered & stm32_write_7900_attention_delayed;


    stm32_7900_command_set_status_access = stm32_data_access & (address_register == STM32_REG_7900_SET_STATUS);
    stm32_7900_command_clear_status_access = stm32_data_access & (address_register == STM32_REG_7900_CLEAR_STATUS);
    stm32_7900_command_set_status = fsmc_write_commit && fsmc_write_address == STM32_REG_7900_SET_STATUS;
    stm32_7900_command_clear_status = fsmc_write_commit && fsmc_write_address == STM32_REG_7900_CLEAR_STATUS;

    stm32_7900_seek_record_access = stm32_data_access & (address_register == STM32_REG_7900_SEEK_RECORD);
    stm32_read_7900_seek_record = stm32_7900_seek_record_access & fsmc_read_valid;


    stm32_irq = stm32_irq_ff & stm32_irq_enable | stm32_data_channel_irq_ff & stm32_data_channel_irq_enable;

    stm32_drq = 1'b0;

    // CHECK count consumption must not request stale DMA data. Optional
    // CHECK DMA starts when the backend explicitly stages a DATA word.
    set_data_channel_flag_buffer = reset_data_channel_encode_ff |
      stm32_write_7900_data_negedge |
      (stm32_read_7900_data_negedge & ~command_is_check_data) |
      ((command_register == 4'b0000) & ~command_channel_control_ff_delayed & command_channel_control_ff);
    stc_data_channel = stc & dsel;
    stc_data_channel_negedge = ~stc_data_channel & stc_data_channel_delayed;
    stc_data_channel_posedge = stc_data_channel & ~stc_data_channel_delayed;  
    seek_record_command = ( command_register == 4'h3) & ioo;
    status_check_command = (command_register == 4'h0) & ioo;
    
    command_is_status_check = ( command_register == 4'h0);
    command_is_write_data = ( command_register == 4'h1);
    command_is_read_data = ( command_register == 4'h2);
    command_is_seek_record = ( command_register == 4'h3);
    command_is_refine_sector = ( command_register == 4'h5);
    command_is_check_data = ( command_register == 4'h6);
    command_is_initalize_data = ( command_register == 4'h9);
    command_is_address_record = ( command_register == 4'hb);
    command_is_seek_record_or_address_record = command_is_seek_record | command_is_address_record;
    seek_or_address_record_command = (command_is_seek_record | command_is_address_record) & csel & stc;
    command_channel_control_ff_posedge = ~command_channel_control_ff_delayed & command_channel_control_ff;
  end

  //--------------------------------------------------------------------------
  // Main sequential logic
  //--------------------------------------------------------------------------
  // Board-reset-only scratchpad, independent of HP POPIO and disk state.
  // Addresses are the values on AD during NADV, not CPU byte addresses.
  always @(posedge clk) begin
    if (reset) test_register <= 16'h0000;
    else if (fsmc_write_commit && fsmc_write_address == STM32_REG_TEST)
      test_register <= fsmc_write_data;
  end

  always @(posedge clk) begin
    if (reset || popio) begin
      address_register <= 0;
      data_channel_flag_buffer_ff <= 1'b1;
      data_channel_flag_ff <= 0;
      command_channel_flag_buffer_ff <= 1'b1;
      command_channel_flag_ff <= 0;
      seek_aborted <= 0;
      command_channel_control_ff <= 0;
      stm32_read_csr_registered <= 0;
      stm32_read_csr_delayed <= 0;
      seeking <= 0;
      command_channel_control_ff_delayed <= 0;
      seek_pending <= 0;
      command_pending <= 0;
      pending_command <= 0;
      pending_address <= 0;
      seek_was_busy <= 0;
      csr_read_flags <= 0;
      captured_command <= 0;
      captured_address <= 0;
      captured_request_valid <= 0;
      seek_request_delayed <= 0;
      seek_record_read_delayed <= 0;
      stm32_data_channel_irq_ff <= 0;
      data_channel_encode_ff <= 0;
      read_dma_ended <= 0;
      discard_read_stc <= 0;
      seek_state <= SEEK_IDLE;
      cylinder_address <= 0;
      reset_data_channel_encode_ff <= 0;
      head_address <= 0;
      sector_address <= 0;
      set_irq_ff <= 0;
      data_error <= 0;
      drive_busy <= 0;
      flagged_cylinder <= 0;
      address_error <= 0;
      end_of_cylinder <= 0;
      not_ready <= RESET_NOT_READY;
      seek_check <= 0;
      data_protect <= 0;
      drive_unsafe <= 0;
      overrun <= 0;
      first_status <= 0;
      stm32_read_7900_data_registered <= 0;
      stm32_read_7900_data_delayed <= 0;
      stm32_write_7900_data_registered <= 0;
      stm32_write_7900_data_delayed <= 0;
      stm32_write_7900_command_status_registered <= 0;
      stm32_write_7900_command_status_delayed <= 0;
      data_interface_input_buffer_register <= 0;
      irq_ff <= 0;
      stc_data_channel_delayed <= 0;
      command_register <= 0;
      drive_select_register <= 0;
      protected_cylinder_register <= 0;
      defective_cylinder_register <= 0;
      stm32_write_7900_attention_registered <= 0;
      stm32_write_7900_attention_delayed <= 0;
      attention_input_register <= 0;
      data_interface_output_buffer_register <= 0;
      if (reset) begin
        stm32_irq_enable <= 0;
        stm32_data_channel_irq_enable <= 0;
      end
      end else begin

        // microcontroller interface

        if (fsmc_address_valid) address_register <= stm32_fsmc_ad_in[3:0];
        
        //--------------------------------------------------------------------
        // Simple flip-flop controls
        //--------------------------------------------------------------------

        // data channel flag buffer flip/flop
        if ((clf & dsel) |  (iak & irq_ff)) data_channel_flag_buffer_ff <= 1'b0;
        else if ((stf & dsel) | (~data_channel_flag_ff & set_data_channel_flag_buffer)) data_channel_flag_buffer_ff <= 1'b1;

        // data channel flag flip/flop
        if (clf & dsel) data_channel_flag_ff <= 1'b0;
        else if (data_channel_flag_buffer_ff & enf) data_channel_flag_ff <= 1'b1;
         
        // command channel flag buffer flip/flop
        if ((clf & csel) |  (iak & irq_ff)) command_channel_flag_buffer_ff <= 1'b0;
        // SEEK address acceptance requests backend service, not HP completion.
        // Its flag is raised by the backend's attention write when positioning
        // finishes. ADDRESS RECORD still completes at the address handshake.
        else if ((stf & csel) | (~command_channel_flag_ff & stm32_write_7900_attention_negedge) |
                 (set_irq_ff & ~command_is_seek_record)) command_channel_flag_buffer_ff <= 1'b1;

        // command channel flag flip/flop
        if (clf & csel) command_channel_flag_ff <= 1'b0;
        else if (command_channel_flag_buffer_ff & enf) command_channel_flag_ff <= 1'b1;
        
        // command channel control flip/flip
        if (((clc | ioo) & csel) | crs) begin
          // STATUS may inspect a moving drive without cancelling its seek.
          // Commands to another drive must also leave that seek running.
          if (crs) seek_aborted <= seek_aborted | seeking;
          else if (!seek_abort_is_status && seeking[seek_abort_drive])
            seek_aborted[seek_abort_drive] <= 1'b1;
          command_channel_control_ff <= 1'b0;
        end
        else if (stc & csel) command_channel_control_ff <= 1'b1;

        stm32_read_csr_registered <= stm32_read_csr;
        stm32_read_csr_delayed <= stm32_read_csr_registered;
        
        if (command_is_seek_record & stc & csel) begin
          //$display("[%0t]>>13210: Seek command initiated drive=%d", $time, drive_select_register);
          seeking[drive_select_register] <= 1'b1;
          seek_aborted[drive_select_register] <= 1'b0;
        end

        // STM32 interface

        // The IRQ is set on the rising edge of the command channel control signal and reset by reading the status register.
        command_channel_control_ff_delayed <= command_channel_control_ff;

        seek_request_delayed <= set_irq_ff;
        seek_record_read_delayed <= stm32_read_7900_seek_record;
        if (seek_record_read_delayed && !stm32_read_7900_seek_record)
          captured_request_valid <= 1'b0;
        if (csr_read_start)
          csr_read_flags <= {stm32_irq_ff, stm32_data_channel_irq_ff};
        if (request_pop) begin
          if (pending_seek) begin
            captured_command <= {4'h3, 10'b0, pending_drive};
            captured_address <= {1'b0, seek_addresses[pending_drive]};
            seek_pending[pending_drive] <= 1'b0;
          end else begin
            captured_command <= pending_command;
            captured_address <= {1'b0, pending_address};
            command_pending <= 1'b0;
          end
          captured_request_valid <= 1'b1;
        end
        // CLC cancels an ordinary command not yet taken by the MCU. A
        // drive's accepted seek survives CLC/CRS and only loses attention.
        if ((clc && csel) || crs) command_pending <= 1'b0;
        if (backend_request) begin
          if (command_is_seek_record) begin
            // A second SEEK selects the new head/sector in the live RAR,
            // but cannot change the drive's original positioning operation.
            if (!seek_was_busy) begin
              seek_addresses[drive_select_register] <= {cylinder_address, head_address, sector_address};
              seek_pending[drive_select_register] <= 1'b1;
            end
          end else begin
            pending_command <= {command_register, 2'b00,
                protected_cylinder_register, defective_cylinder_register,
                2'b00, seek_aborted, drive_select_register};
            pending_address <= {cylinder_address, head_address, sector_address};
            command_pending <= 1'b1;
          end
        end

        // The final READ DMA input carries CLC instead of another STC.
        // Preserve the software response margin for normal words, but reject
        // a later STC while the command/sector is still completing (SIMH).
        if (crs) begin
          read_dma_ended <= 0;
          discard_read_stc <= 0;
        end else begin
          if (command_channel_control_ff_posedge) read_dma_ended <= 0;
          else if (clc && dsel && command_is_read_data &&
                   command_channel_control_ff && !command_channel_flag_ff)
            read_dma_ended <= 1;
          // Classify once at the start of the HP pulse. Completion or a new
          // command during a wide pulse must not turn a rejected request valid.
          if (stc_data_channel_posedge) begin
            discard_read_stc <= late_read_request;
            if (late_read_request) overrun[drive_select_register] <= 1;
          end else if (stc_data_channel_negedge) discard_read_stc <= 0;
        end
        if (stm32_read_7900_data_negedge | stm32_write_7900_data_negedge) stm32_data_channel_irq_ff <= 1'b0;
        else if (stc_data_channel_negedge && !discard_read_stc) stm32_data_channel_irq_ff <= 1'b1;

        if (crs | reset_data_channel_encode_ff) data_channel_encode_ff <= 1'b0;
        else if (stc_data_channel_posedge) data_channel_encode_ff <= 1'b1;

        if (stm32_write_csr) begin
            stm32_irq_enable <= fsmc_write_data[8];
            stm32_data_channel_irq_enable <= fsmc_write_data[9];
        end

        case (seek_state)
          SEEK_IDLE:
            begin
              if (seek_or_address_record_command) begin
                seek_state <= SEEK_GOT_SEEK_CMD;  
              end
            end
          SEEK_GOT_SEEK_CMD:
            begin
              if (crs) begin
                seek_state <= SEEK_IDLE;
              end 
              else if (data_channel_encode_ff) begin
                cylinder_address <= data_interface_output_buffer_register[7:0];  
                reset_data_channel_encode_ff <= 1'b1;
                seek_state <= SEEK_STORED_DATA;
              end
            end
          SEEK_STORED_DATA:
            begin
              if (crs) begin
                seek_state <= SEEK_IDLE;
              end 
              else if (!(stc & dsel) && !(clf & dsel)) begin
                seek_state <= SEEK_GET_NEXT_WORD;  
                reset_data_channel_encode_ff <= 1'b0;
              end 
            end 
          SEEK_GET_NEXT_WORD:
            begin
              if (crs) begin
                seek_state <= SEEK_IDLE;
              end
              else if (data_channel_encode_ff) begin
                head_address <= data_interface_output_buffer_register[9:8];
                sector_address <=  data_interface_output_buffer_register[4:0];
                reset_data_channel_encode_ff <= 1'b1; 
                set_irq_ff <= 1'b1;
                // Positioning starts when the final address word is accepted
                // (13210A manual 3-45), even if backend polling is delayed.
                if (command_is_seek_record) begin
                  seek_was_busy <= drive_busy[drive_select_register];
                  if (!drive_busy[drive_select_register]) seek_check[drive_select_register] <= 1'b0;
                  drive_busy[drive_select_register] <= 1'b1;
                end
                seek_state <= SEEK_GOT_SECOND_WORD;
              end
            end
          SEEK_GOT_SECOND_WORD:
            begin
              // STC precedes CLF in STC,C. Hold the acknowledgement until
              // both phases have ended so the later CLF cannot erase it.
              if (!(stc & dsel) && !(clf & dsel)) begin
                seek_state <= SEEK_IDLE;
                set_irq_ff <= 1'b0;
                reset_data_channel_encode_ff <= 1'b0; 
              end  
            end
          default:
            seek_state <= SEEK_IDLE;
        endcase


        if (stm32_7900_command_set_status) begin
          if (fsmc_write_data[0]) data_error[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[1]) drive_busy[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[2]) flagged_cylinder[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[3]) address_error[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[4]) end_of_cylinder[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[5]) not_ready[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[6]) seek_check[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[7]) data_protect[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[8]) drive_unsafe[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[9]) overrun[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[10]) first_status[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[11]) seeking[fsmc_write_data[15:14]] <= 1'b1;
          if (fsmc_write_data[12]) seek_aborted[fsmc_write_data[15:14]] <= 1'b1;
        end

        if (stm32_7900_command_clear_status) begin
          if (fsmc_write_data[0]) data_error[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[1]) drive_busy[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[2]) flagged_cylinder[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[3]) address_error[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[4]) end_of_cylinder[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[5]) not_ready[fsmc_write_data[15:14]] <= 1'b0;
          // A valid SEEK clears Seek Check when accepted above. Do not let
          // its delayed MCU clear erase a newer busy-SEEK error. Clearing
          // Busy too (including initialization) may clear both status bits.
          if (fsmc_write_data[6] && (!drive_busy[fsmc_write_data[15:14]] || fsmc_write_data[1]))
            seek_check[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[7]) data_protect[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[8]) drive_unsafe[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[9]) overrun[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[10]) first_status[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[11]) seeking[fsmc_write_data[15:14]] <= 1'b0;
          if (fsmc_write_data[12]) seek_aborted[fsmc_write_data[15:14]] <= 1'b0;
        end

        // Busy-SEEK wins over a simultaneous older backend status clear.
        if (backend_request && command_is_seek_record && seek_was_busy)
          seek_check[drive_select_register] <= 1'b1;

        stm32_read_7900_data_registered <= stm32_read_7900_data;
        stm32_read_7900_data_delayed <=  stm32_read_7900_data_registered;

        stm32_write_7900_data_registered <= stm32_write_7900_data;
        stm32_write_7900_data_delayed <= stm32_write_7900_data_registered;

        stm32_write_7900_command_status_registered <= stm32_write_7900_command_status;
        stm32_write_7900_command_status_delayed <= stm32_write_7900_command_status_registered;

        if ((command_register == 4'b0000) & ~command_channel_control_ff_delayed & command_channel_control_ff) begin
            data_interface_input_buffer_register <= { 1'b0, first_status[drive_select_register], overrun[drive_select_register], 1'b0, drive_unsafe[drive_select_register], data_protect[drive_select_register], 1'b0, seek_check[drive_select_register], 1'b0, not_ready[drive_select_register], end_of_cylinder[drive_select_register], address_error[drive_select_register], flagged_cylinder[drive_select_register], drive_busy[drive_select_register], data_error[drive_select_register], any_error};
            address_error[drive_select_register] <= 1'b0;
            end_of_cylinder[drive_select_register] <= 1'b0;
            overrun[drive_select_register] <= 1'b0;
            first_status[drive_select_register] <= 1'b0;
        end
        else if (stm32_write_7900_data) begin
            data_interface_input_buffer_register <= fsmc_write_data;
        end  

        // irq flip/flop
        if (sir & prh & command_channel_flag_buffer_ff & ien & command_channel_flag_ff & command_channel_control_ff) irq_ff <= 1'b1;
        else if (enf) irq_ff <= 1'b0;

        stc_data_channel_delayed <= stc_data_channel;

        if (ioo & csel) begin
            command_register <= iob_out[15:12];
            drive_select_register <= iob_out[1:0];
            protected_cylinder_register <= iob_out[9];
            defective_cylinder_register <= iob_out[8];
        end
        stm32_write_7900_attention_registered <= stm32_write_7900_attention;
        stm32_write_7900_attention_delayed <= stm32_write_7900_attention_registered;
        
        if (crs | seek_record_command | status_check_command) attention_input_register[0] <=1'b0;
        //else if (drv0_sel) attention_input_register[0] <=1'b1;
        else if (stm32_write_7900_attention) attention_input_register[0] <= fsmc_write_data[0] | attention_input_register[0];

        if (crs | seek_record_command | status_check_command) attention_input_register[1] <=1'b0;
        //else if (drv1_sel) attention_input_register[1] <=1'b1;
        else if (stm32_write_7900_attention) attention_input_register[1] <= fsmc_write_data[1] | attention_input_register[1];

        if (crs | seek_record_command | status_check_command) attention_input_register[2] <=1'b0;
        //else if (drv2_sel) attention_input_register[2] <=1'b1;
        else if (stm32_write_7900_attention) attention_input_register[2] <= fsmc_write_data[2] | attention_input_register[2];

        if (crs | seek_record_command | status_check_command) attention_input_register[3] <=1'b0;
        //else if (drv3_sel) attention_input_register[3] <=1'b1;
        else if (stm32_write_7900_attention) attention_input_register[3] <= fsmc_write_data[3] | attention_input_register[3];

        if (dsel & ioo) data_interface_output_buffer_register <= iob_out;
      end
    end


  // One read mux and one output enable. Tri-states belong at the FPGA boundary.
  assign stm32_fsmc_ad_oe = ~stm32_fsmc_ne & stm32_fsmc_nadv &
                            ~stm32_fsmc_noe & stm32_fsmc_nwe;
  always @* begin
    stm32_fsmc_ad_out = 16'h0000;
    case (address_register)
      STM32_REG_TEST: stm32_fsmc_ad_out = test_register;
      STM32_REG_CSR:
        stm32_fsmc_ad_out = (stm32_read_csr || stm32_read_csr_registered) ?
          {8'h00, csr_read_flags, 6'h00} : {8'h00, stm32_irq_ff, stm32_data_channel_irq_ff, 6'h00};
      STM32_REG_7900_COMMAND_STATUS:
        stm32_fsmc_ad_out = captured_request_valid ?
          {captured_command[15:6], seek_aborted, captured_command[1:0]} :
          {command_register, 2'b00, protected_cylinder_register,
          defective_cylinder_register, 2'b00, seek_aborted, drive_select_register};
      STM32_REG_7900_DATA:
        stm32_fsmc_ad_out = data_interface_output_buffer_register;
      STM32_REG_7900_ATTENTION:
        stm32_fsmc_ad_out = {12'h000, attention_input_register};
      STM32_REG_7900_SEEK_RECORD:
        stm32_fsmc_ad_out = captured_request_valid ? captured_address :
          {1'b0, cylinder_address, head_address, sector_address};
      default: stm32_fsmc_ad_out = 16'h0000;
    endcase
  end

endmodule
