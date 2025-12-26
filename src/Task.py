import subprocess
import ctypes
import sys
import time  # 用于测试时的短暂延迟，确保操作生效


class Task:

    def is_admin(self):
        """检查是否以管理员权限运行"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def create_scheduled_task(self, task_name, exe_path):
        """
        创建计划任务，成功返回True，失败返回False
        task_name: 任务名称
        exe_path: 程序路径
        """
        if not self.is_admin():
            # 提权重启程序
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, __file__, None, 1
            )
            return False  # 提权后程序重启，此处返回无实际意义

        # 构造创建任务计划的命令
        task_command = (
            f'schtasks /create /tn "{task_name}" /tr "{exe_path}" /sc onlogon '
            f'/rl highest /f'
        )

        try:
            # 执行命令
            subprocess.run(task_command, shell=True, check=True)
            # print("任务计划创建成功，程序将在登录时以管理员权限自动启动")
            return True  # 创建成功返回True
        except subprocess.CalledProcessError as e:
            # print(f"任务计划创建失败：{e}")
            return False
        except Exception as e:
            # print(f"发生错误：{str(e)}")
            return False

    def delete_scheduled_task(self, task_name):
        """删除指定的计划任务，成功返回True，失败返回False"""
        if not self.is_admin():
            # 提权重启程序
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, __file__, None, 1
            )
            return False  # 提权后程序会重启，此处返回无实际意义

        # 构造删除任务的命令
        delete_command = f'schtasks /delete /tn "{task_name}" /f'

        try:
            # 执行删除命令
            subprocess.run(
                delete_command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # print(f"任务计划「{task_name}」已成功删除")
            return True  # 删除成功返回True
        except subprocess.CalledProcessError as e:
            # print(f"删除任务失败：{e.stderr}")
            return False
        except Exception as e:
            # print(f"发生错误：{str(e)}")
            return False

    def check_task_exists(self, task_name):
        try:
            # 查询单个任务的详细信息
            subprocess.run(
                f'schtasks /query /tn "{task_name}" /v /fo list',
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # 若未抛出异常，说明任务存在且查询成功
            return True
        except subprocess.CalledProcessError:
            # 任务不存在或查询失败（如权限不足）
            return False

    def test_task_operations(self, test_task_name, test_exe_path):
        """
        测试任务的创建、查询、删除全流程
        test_task_name: 测试用的任务名称
        test_exe_path: 测试用的程序路径
        """
        print("\n===== 开始测试任务操作 =====")

        # 1. 检查初始状态（任务应不存在）
        initial_exists = self.check_task_exists(test_task_name)
        print(f"测试前任务是否存在：{initial_exists}（预期：False）")

        # 2. 创建任务
        print("\n----- 测试创建任务 -----")
        create_success = self.create_scheduled_task(test_task_name, test_exe_path)
        print(f"创建任务结果：{create_success}（预期：True）")

        # 短暂延迟，确保任务创建生效
        time.sleep(1)

        # 3. 检查任务是否存在
        print("\n----- 测试查询任务 -----")
        exists_after_create = self.check_task_exists(test_task_name)
        print(f"创建后任务是否存在：{exists_after_create}（预期：True）")

        # 4. 删除任务
        print("\n----- 测试删除任务 -----")
        delete_success = self.delete_scheduled_task(test_task_name)
        print(f"删除任务结果：{delete_success}（预期：True）")

        # 短暂延迟，确保任务删除生效
        time.sleep(1)

        # 5. 检查删除后状态
        print("\n----- 测试删除后状态 -----")
        exists_after_delete = self.check_task_exists(test_task_name)
        print(f"删除后任务是否存在：{exists_after_delete}（预期：False）")

        print("\n===== 测试结束 =====")

        # 验证所有步骤是否符合预期
        return (
                not initial_exists and
                create_success and
                exists_after_create and
                delete_success and
                not exists_after_delete
        )


# 测试代码
if __name__ == "__main__":
    # 实例化Task类
    task_manager = Task()

    # 测试用的任务名称和程序路径（替换为实际存在的程序路径）
    test_task = "iGameFansAutoStart"  # 用独特名称避免冲突
    test_exe = r"C:\Users\w1862\PycharmProjects\iGameFans\dist\iGameFans.exe"

    # 执行测试
    test_result = task_manager.test_task_operations(test_task, test_exe)

    # 输出最终测试结果
    if test_result:
        print("\n✅ 所有测试步骤均符合预期！")
    else:
        print("\n❌ 部分测试步骤不符合预期，请检查日志。")