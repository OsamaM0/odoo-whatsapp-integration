from typing_extensions import List




def bassam(numbers: List[str]) -> int:
    bassam_sum = 0
    for number in numbers:
        bassam_sum += number
    
    return bassam_sum


print(bassam([1,2,3]))