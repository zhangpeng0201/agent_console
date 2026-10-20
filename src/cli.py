from handle import handle


def main():
    while True:
        user_input = input("请输入内容（'输入quit退出'）: ").strip()
        if user_input == "":
            continue
        if user_input in ("quit", 'q'):
            break
        reply = handle(user_input)
        print(reply)

if __name__ == '__main__':
    main()