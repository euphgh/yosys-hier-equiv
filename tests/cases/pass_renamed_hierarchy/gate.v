module top(input wire a, input wire b, output wire y);
  gate_generated_name u_stage (.a(a), .b(b), .y(y));
endmodule

module gate_generated_name(input wire a, input wire b, output wire y);
  assign y = a & b;
endmodule

