module top(input a, input b, output y);
  gate_stage u_gate(.a(a), .b(b), .y(y));
endmodule

module gate_stage(input a, input b, output y);
  assign y = a ^ b;
endmodule
