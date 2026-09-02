module top(input wire a, output wire y);
  gold_mid u_mid (.a(a), .y(y));
endmodule

module gold_mid(input wire a, output wire y);
  gold_leaf u_leaf (.a(a), .y(y));
endmodule

module gold_leaf(input wire a, output wire y);
  assign y = ~a;
endmodule
