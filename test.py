from doctest import FAIL_FAST


first_var = '123'
second_var = '456'
third_var = 0


def check_list():
    list = (
        first_var,
        second_var,
        third_var
    )
    for var in list:
        if var == 0 or var == '':
            print(var)
    if 0 in list or '' in list:
        return False
    return True

print(check_list())
