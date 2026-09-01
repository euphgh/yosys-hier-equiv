module top(input wire a, output wire y);
  parameter_cell #(.INVERT(1)) u_cell (.a(a), .y(y));
endmodule

