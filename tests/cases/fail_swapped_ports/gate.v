module top(input wire a, input wire b, output wire y);
  asymmetric_cell u_cell (.a(b), .b(a), .y(y));
endmodule

