module top(input a, input b, output y);
  gold_stage u_gold(.a(a), .b(b), .y(y));
endmodule

module gold_stage(input a, input b, output y);
  assign y = a ^ b;
endmodule
