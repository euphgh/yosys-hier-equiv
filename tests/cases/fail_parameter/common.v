module parameter_cell #(
  parameter INVERT = 0
) (
  input wire a,
  output wire y
);
  assign y = INVERT ? ~a : a;
endmodule

