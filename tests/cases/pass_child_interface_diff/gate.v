module top(input wire a, output wire y);
  gate_stage u_stage (.q(a), .y(y));
endmodule

module gate_stage(input wire q, output wire y);
  assign y = ~q;
endmodule
