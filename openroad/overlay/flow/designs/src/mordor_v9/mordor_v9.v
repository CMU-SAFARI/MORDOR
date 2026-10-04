`timescale 1ns / 1ps
// Per-request blacklist models on top of a memory-controller request-queue array.
//
//   MODE = 0  baseline : the MC entry array alone (row-addr + valid + a read port
//                        and a per-entry "ready" = valid). This is the array we
//                        measure the two mechanisms against.
//   MODE = 1  CAM      : every MC entry's row address is searched against ALL PROQ
//                        entries (compare-everything-vs-everything) -> a per-entry
//                        blacklist bit; ready = valid & ~blacklisted.
// overhead(impl) = area/leakage(MODE=k) - area/leakage(MODE=0).
//
// The MC is modelled only as the array of row-address registers it needs to be for
// the blacklist mechanism (not the full controller). A real MC entry is wider, so
// the overhead RELATIVE to a full entry would be smaller -- the numbers here are the
// blacklist mechanism's cost against the address-holding portion of the queue.
module mordor_v9 #(
  parameter integer MC_ENTRIES   = 64,
  parameter integer PROQ_ENTRIES = 32,
  parameter integer ADDR_W       = 24,
  parameter integer MODE         = 0
)(
  input  wire                            clk,
  input  wire                            rst,
  // install a request's row address into MC entry mc_w_idx
  input  wire                            mc_w_en,
  input  wire [$clog2(MC_ENTRIES)-1:0]   mc_w_idx,
  input  wire [ADDR_W-1:0]               mc_w_addr,
  input  wire                            mc_w_val,
  // PRO enqueue / dequeue events (carry the aggressor row address)
  input  wire                            pro_en,
  input  wire                            pro_deq,
  input  wire [ADDR_W-1:0]               pro_addr,
  input  wire [$clog2(PROQ_ENTRIES)-1:0] proq_idx,    // PROQ slot for CAM mode
  // scheduler read-out (keeps the address array observable in ALL modes)
  input  wire [$clog2(MC_ENTRIES)-1:0]   issue_idx,
  output reg  [ADDR_W-1:0]               issued_addr_o,
  // per-entry "ready" = valid AND not blacklisted
  output reg  [MC_ENTRIES-1:0]           ready_o
);
  genvar gi, gj;

  // ---- the MC request-queue array (present in ALL modes = the baseline) ------
  reg [ADDR_W-1:0]     mc_addr [0:MC_ENTRIES-1];
  reg [MC_ENTRIES-1:0] mc_valid;
  always @(posedge clk) begin
    if (rst) mc_valid <= {MC_ENTRIES{1'b0}};
    else if (mc_w_en) begin
      mc_addr[mc_w_idx]  <= mc_w_addr;
      mc_valid[mc_w_idx] <= mc_w_val;
    end
  end
  always @(posedge clk) issued_addr_o <= mc_addr[issue_idx];

  // ---- blacklist mechanism (mode-specific) -----------------------------------
  wire [MC_ENTRIES-1:0] ready_c;
  generate
  if (MODE == 1) begin : G_CAM
    reg [ADDR_W-1:0]       proq_addr [0:PROQ_ENTRIES-1];
    reg [PROQ_ENTRIES-1:0] proq_valid;
    always @(posedge clk) begin
      if (rst) proq_valid <= {PROQ_ENTRIES{1'b0}};
      else begin
        if (pro_en)  begin proq_addr[proq_idx] <= pro_addr; proq_valid[proq_idx] <= 1'b1; end
        if (pro_deq) proq_valid[proq_idx] <= 1'b0;
      end
    end
    // compare EVERY MC entry against EVERY PROQ entry
    wire [MC_ENTRIES-1:0] blk;
    for (gi = 0; gi < MC_ENTRIES; gi = gi + 1) begin : CI
      wire [PROQ_ENTRIES-1:0] m;
      for (gj = 0; gj < PROQ_ENTRIES; gj = gj + 1) begin : CJ
        assign m[gj] = proq_valid[gj] && (proq_addr[gj] == mc_addr[gi]);
      end
      assign blk[gi] = |m;
    end
    assign ready_c = mc_valid & ~blk;
  end
  else begin : G_BASE
    assign ready_c = mc_valid;
  end
  endgenerate

  always @(posedge clk) ready_o <= rst ? {MC_ENTRIES{1'b0}} : ready_c;
endmodule
