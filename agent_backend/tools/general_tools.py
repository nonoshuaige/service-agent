from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """执行数学计算。当用户要求计算数学表达式时调用。

    Args:
        expression: 数学表达式，如 '2+3*4'
    """
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算失败: {str(e)}"


GENERAL_TOOLS = [calculator]
