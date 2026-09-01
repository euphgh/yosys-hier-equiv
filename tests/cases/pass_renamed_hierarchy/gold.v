module top(input wire a, input wire b, output wire y);
  gold_stage u_stage (.a(a), .b(b), .y(y));
endmodule

module gold_stage(input wire a, input wire b, output wire y);
  assign y = a & b;
endmodule

