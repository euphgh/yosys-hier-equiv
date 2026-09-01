module top(input [1:0] a, output [1:0] y);
  gate_stage u_stage0(.a(a[0]), .y(y[0]));
  gate_stage u_stage1(.a(a[1]), .y(y[1]));
endmodule

module gate_stage(input a, output y);
  assign y = a ^ 1'b1;
endmodule
