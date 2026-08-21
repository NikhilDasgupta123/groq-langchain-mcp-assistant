def register_calculator_tools(mcp):
    @mcp.tool()
    def add_numbers(a: float, b: float) -> float:
        """Add two numbers together."""
        return a + b
