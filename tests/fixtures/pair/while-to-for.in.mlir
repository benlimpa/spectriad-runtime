func.func @rotate_ne(%lb: i64, %ub: i64, %step: i64, %init: f32, %buf: memref<?xf32>) -> f32 {
  %r:2 = scf.while (%iv = %lb, %acc = %init) : (i64, f32) -> (i64, f32) {
    %idx = arith.index_cast %iv : i64 to index
    %x = memref.load %buf[%idx] : memref<?xf32>
    %acc_next = arith.addf %acc, %x : f32
    %iv_next = arith.addi %iv, %step : i64
    %cond = arith.cmpi ne, %iv_next, %ub : i64
    scf.condition(%cond) %iv_next, %acc_next : i64, f32
  } do {
  ^bb0(%iv_next: i64, %acc_next: f32):
    scf.yield %iv_next, %acc_next : i64, f32
  }
  return %r#1 : f32
}

func.func @rotate_ult(%lb: i64, %ub: i64, %init: i64) -> i64 {
  %c1 = arith.constant 1 : i64
  %r:2 = scf.while (%iv = %lb, %sum = %init) : (i64, i64) -> (i64, i64) {
    %sum_next = arith.addi %sum, %iv : i64
    %iv_next = arith.addi %iv, %c1 : i64
    %cond = arith.cmpi ult, %iv_next, %ub : i64
    scf.condition(%cond) %iv_next, %sum_next : i64, i64
  } do {
  ^bb0(%iv_next: i64, %sum_next: i64):
    scf.yield %iv_next, %sum_next : i64, i64
  }
  return %r#1 : i64
}

func.func @keep_sle(%lb: i64, %ub: i64, %init: i64) -> i64 {
  %c1 = arith.constant 1 : i64
  %r:2 = scf.while (%iv = %lb, %sum = %init) : (i64, i64) -> (i64, i64) {
    %sum_next = arith.addi %sum, %iv : i64
    %iv_next = arith.addi %iv, %c1 : i64
    %cond = arith.cmpi sle, %iv_next, %ub : i64
    scf.condition(%cond) %iv_next, %sum_next : i64, i64
  } do {
  ^bb0(%iv_next: i64, %sum_next: i64):
    scf.yield %iv_next, %sum_next : i64, i64
  }
  return %r#1 : i64
}
