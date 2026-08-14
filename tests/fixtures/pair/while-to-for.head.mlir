module {
  func.func @rotate_ne(%arg0: i64, %arg1: i64, %arg2: i64, %arg3: f32, %arg4: memref<?xf32>) -> f32 {
    %0 = scf.for %arg5 = %arg0 to %arg1 step %arg2 iter_args(%arg6 = %arg3) -> (f32)  : i64 {
      %1 = arith.index_cast %arg5 : i64 to index
      %2 = memref.load %arg4[%1] : memref<?xf32>
      %3 = arith.addf %arg6, %2 : f32
      scf.yield %3 : f32
    }
    return %0 : f32
  }
  func.func @rotate_ult(%arg0: i64, %arg1: i64, %arg2: i64) -> i64 {
    %c1_i64 = arith.constant 1 : i64
    %0 = scf.for %arg3 = %arg0 to %arg1 step %c1_i64 iter_args(%arg4 = %arg2) -> (i64)  : i64 {
      %1 = arith.addi %arg4, %arg3 : i64
      scf.yield %1 : i64
    }
    return %0 : i64
  }
  func.func @keep_sle(%arg0: i64, %arg1: i64, %arg2: i64) -> i64 {
    %c1_i64 = arith.constant 1 : i64
    %0:2 = scf.while (%arg3 = %arg0, %arg4 = %arg2) : (i64, i64) -> (i64, i64) {
      %1 = arith.addi %arg4, %arg3 : i64
      %2 = arith.addi %arg3, %c1_i64 : i64
      %3 = arith.cmpi sle, %2, %arg1 : i64
      scf.condition(%3) %2, %1 : i64, i64
    } do {
    ^bb0(%arg3: i64, %arg4: i64):
      scf.yield %arg3, %arg4 : i64, i64
    }
    return %0#1 : i64
  }
}

