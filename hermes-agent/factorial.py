def factorial(n):
    """Calculate factorial of n using iterative approach"""
    if n < 0:
        return None
    elif n == 0 or n == 1:
        return 1
    else:
        result = 1
        for i in range(2, n + 1):
            result *= i
        return result

# Calculate factorial of 10
number = 10
result = factorial(number)
print(f"The factorial of {number} is: {result}")
