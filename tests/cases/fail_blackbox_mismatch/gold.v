(* blackbox *)
module bb_cell(input wire a, output wire y);
endmodule

module top(input wire a, output wire y);
  bb_cell u_bb (.a(a), .y(y));
endmodule
