module top(input a, output y);
  gate_stage u_stage(.a(a), .b(1'b0), .y(y));
endmodule

module gate_stage(input a, input b, output y);
  assign y = a ^ b;
endmodule
