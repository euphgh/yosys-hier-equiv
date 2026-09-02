`include "shared_cell.vh"

module top(input wire a, input wire b, output wire y);
  shared_cell u_cell (.a(a), .b(b), .y(y));
endmodule
