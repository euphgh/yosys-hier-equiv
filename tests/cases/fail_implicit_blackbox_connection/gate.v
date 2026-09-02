module top(input wire a, input wire b, output wire y);
  sub_module u_sub (.in(b), .out(y));
endmodule
