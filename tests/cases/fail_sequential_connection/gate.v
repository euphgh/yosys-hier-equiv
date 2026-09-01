module top(
  input wire clk,
  input wire rst,
  input wire a,
  input wire b,
  output reg q
);
  always @(posedge clk) begin
    if (rst)
      q <= 1'b0;
    else
      q <= b;
  end
endmodule

