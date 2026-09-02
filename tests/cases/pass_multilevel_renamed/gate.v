module top(input wire a, output wire y);
  gate_mid u_mid (.a(a), .y(y));
endmodule

module gate_mid(input wire a, output wire y);
  gate_leaf u_leaf (.a(a), .y(y));
endmodule

module gate_leaf(input wire a, output wire y);
  assign y = ~a;
endmodule
