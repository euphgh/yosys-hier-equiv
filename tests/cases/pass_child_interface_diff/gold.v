module top(input wire a, output wire y);
  gold_stage u_stage (.p(a), .y(y));
endmodule

module gold_stage(input wire p, output wire y);
  assign y = ~p;
endmodule
