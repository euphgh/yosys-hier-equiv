module top(input wire a, output wire y);
  gate_wrap u_wrap (.a(a), .y(y));
endmodule

module gate_wrap(input wire a, output wire y);
  gate_stage u_stage (.a(a), .b(1'b0), .y(y));
endmodule

module gate_stage(input wire a, input wire b, output wire y);
  assign y = a ^ b;
endmodule
