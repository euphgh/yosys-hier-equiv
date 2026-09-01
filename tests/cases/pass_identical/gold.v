module top(input wire a, input wire b, output wire y);
  stage u_stage (.a(a), .b(b), .y(y));
endmodule

module stage(input wire a, input wire b, output wire y);
  assign y = a ^ b;
endmodule

