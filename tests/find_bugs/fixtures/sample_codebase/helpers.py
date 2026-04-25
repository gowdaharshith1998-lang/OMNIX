def unsafe_div(x: int, y: int) -> int:
    return x // y  # y can be 0; PBT should find this
