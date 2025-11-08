import os
import re
import logging
import sys # 导入 sys 模块，用于日志重定向到 stdout
from flask import Flask, render_template, request, jsonify

# ==================== 配置 ====================
# 获取当前文件 (api/index.py) 的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 数据文件 (代码表) 将放在项目根目录下的 'data' 文件夹中
# '..' 表示从 'api' 目录向上一个级别，即项目根目录
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')

code_table_path = os.path.join(DATA_DIR, "代码表.txt")
subway_code_table_path = os.path.join(DATA_DIR, "和平地铁美化代码.h")

# 在 Vercel 的无服务器环境中，文件系统是只读且短暂的
# 因此，日志不能写入本地文件，配置也不能持久化保存到本地文件。
# Vercel 会自动捕获发送到 stdout/stderr 的日志。
# 对于配置保存功能，需要外部持久化存储（如数据库或云存储）。
# 在此示例中，我们禁用本地文件日志和本地配置保存功能。

item_dict = {}          # 所有 ID → 信息字典 {name, type, parent}
main_weapon_dict = {}   # 主枪 ID → 名称
sub_to_main_dict = {}   # 子件 ID → 主枪 ID
subway_item_dict = {}   # 新增：地铁美化 ID → 信息字典 {name, hex_code}

# ==================== 日志配置 (已简化，确保 INFO 级别并输出到 stdout) ====================
def setup_logging():
    # 移除创建 LOG_DIR 的代码，因为我们不写入本地文件
    logging.basicConfig(
        # 移除 filename 参数，日志将默认输出到 stderr，通过 stream=sys.stdout 明确指定
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        encoding="utf-8",
        stream=sys.stdout # 将日志重定向到标准输出
    )
    logging.getLogger(__name__).info("Vercel 日志文件配置完成 (输出到 stdout)")

setup_logging() # 确保日志在应用启动时配置
logger = logging.getLogger(__name__)


# ==================== 代码表加载辅助函数 ====================
def parse_generic_code_table(file_path, encoding):
    """解析常规物品代码表文件。"""
    parsed_items = {}
    main_weapons = {}
    sub_to_main = {}

    try:
        with open(file_path, 'r', encoding=encoding) as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(" -- ")]
                if len(parts) < 4:
                    logger.warning(f"通用代码表格式不正确，跳过行: {line}")
                    continue
                try:
                    id1, id2, name = int(parts[0]), int(parts[1]), parts[2]
                    type_hint = "主件"
                    if any(k in name for k in ["弹匣"]):
                        type_hint = "弹匣"
                    elif any(k in name for k in ["枪口"]):
                        type_hint = "枪口"
                    elif any(k in name for k in ["握把"]):
                        type_hint = "握把"
                    elif any(k in name for k in ["瞄具", "瞄准镜", "机瞄"]):
                        type_hint = "机瞄"

                    parent_id = None
                    if type_hint != "主件":
                        parent_id = id1
                    else:
                        parent_id = None

                    parsed_items[id2] = {"name": name, "type": type_hint, "parent": parent_id}
                    if type_hint == "主件":
                        main_weapons[id2] = name
                    else:
                        sub_to_main[id2] = parent_id
                except ValueError:
                    logger.warning(f"通用代码表解析错误，无法转换ID: {line}")
    except FileNotFoundError:
        logger.error(f"错误: 通用代码表文件未找到或路径不正确: {file_path}")
    except Exception as e:
        logger.exception(f"解析通用代码表时发生未知错误: {e}")
    return parsed_items, main_weapons, sub_to_main

def parse_subway_code_table_file(file_path, encoding):
    """解析地铁美化代码表文件。"""
    parsed_subway_items = {}
    subway_pattern = re.compile(r"\{(\d+)\}--\{\d+\}--\[([^\]]+)\]--\[(0x[0-9a-fA-F]+)\]")

    try:
        with open(file_path, 'r', encoding=encoding) as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                match = subway_pattern.match(line)
                if match:
                    try:
                        item_id = int(match.group(1))
                        name = match.group(2)
                        hex_code = match.group(3)
                        parsed_subway_items[item_id] = {"name": name, "hex_code": hex_code}
                    except ValueError:
                        logger.warning(f"地铁代码表解析错误，无法转换ID或Hex Code: {line}")
                else:
                    logger.warning(f"地铁代码表格式不匹配，跳过行: {line}")
    except FileNotFoundError:
        logger.error(f"错误: 地铁美化代码表文件未找到或路径不正确: {file_path}")
    except Exception as e:
        logger.exception(f"解析地铁美化代码表时发生未知错误: {e}")
    return parsed_subway_items

def load_code_table():
    """加载所有配置代码表。"""
    global item_dict, main_weapon_dict, sub_to_main_dict, subway_item_dict

    # 在重新加载前清空所有字典
    item_dict = {}
    main_weapon_dict = {}
    sub_to_main_dict = {}
    subway_item_dict = {}

    # 加载通用物品代码表
    try:
        temp_item_dict, temp_main_weapon_dict, temp_sub_to_main_dict = parse_generic_code_table(code_table_path, 'utf-8')
        item_dict.update(temp_item_dict)
        main_weapon_dict.update(temp_main_weapon_dict)
        sub_to_main_dict.update(temp_sub_to_main_dict)
    except UnicodeDecodeError:
        logger.warning(f"通用代码表 UTF-8 解码失败，尝试 GBK 解码文件: {code_table_path}")
        temp_item_dict, temp_main_weapon_dict, temp_sub_to_main_dict = parse_generic_code_table(code_table_path, 'gbk')
        item_dict.update(temp_item_dict)
        main_weapon_dict.update(temp_main_weapon_dict)
        sub_to_main_dict.update(temp_sub_to_main_dict)
    except Exception as e:
        logger.error(f"加载通用代码表时发生错误: {e}")


    # 加载地铁美化代码表
    try:
        temp_subway_item_dict = parse_subway_code_table_file(subway_code_table_path, 'utf-8')
        subway_item_dict.update(temp_subway_item_dict)
    except UnicodeDecodeError:
        logger.warning(f"地铁美化代码表 UTF-8 解码失败，尝试 GBK 解码文件: {subway_code_table_path}")
        temp_subway_item_dict = parse_subway_code_table_file(subway_code_table_path, 'gbk')
        subway_item_dict.update(temp_subway_item_dict)
    except Exception as e:
        logger.error(f"加载地铁美化代码表时发生错误: {e}")

    logger.info(f"加载完成: 总物品 {len(item_dict)}, 主枪 {len(main_weapon_dict)}, 地铁美化 {len(subway_item_dict)}")

# ==================== 查询函数 ====================
def query_item(codes):
    """根据ID查询物品名称，支持通用物品和地铁美化物品。"""
    results = []
    logger.debug(f"开始查询 ID 列表: {codes}")
    for code in codes:
        item_info = item_dict.get(code)
        subway_info = subway_item_dict.get(code) # 同时检查地铁代码表
        if item_info:
            results.append(item_info["name"])
        elif subway_info:
            results.append(f"{subway_info['name']} (地铁, {subway_info['hex_code']})")
        else:
            results.append(f"未找到ID {code}")
            logger.warning(f"未找到 ID: {code}")
    logger.info(f"查询结果: {results}")
    return ", ".join(results)

# ==================== Flask 应用 ====================
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, '..', 'templates')) # 指定模板文件夹路径

# 在Vercel上，应用启动时会执行这里的代码。
# 确保在 app 实例创建后立即加载代码表。
load_code_table()
logger.info("代码表在 Flask 应用启动时已加载。")


@app.route('/', methods=['GET', 'POST'])
def index():
    final_text = ""
    error_message = ""
    if request.method == 'POST':
        user_input = request.form.get('user_input', '')
        logger.info(f"用户输入:\n{user_input}")
        lines = user_input.split("\n")
        results = []

        # 检查是否至少有一个代码表成功加载
        if not item_dict and not subway_item_dict:
            error_message = "物品代码表和地铁美化代码表均未加载，请联系管理员检查服务器日志。"
            logger.error("代码表未加载，无法处理用户请求。")
        else:
            for line in lines:
                stripped_line = line.strip()
                if not stripped_line:
                    results.append("")
                    continue

                id_match = re.match(r"^\s*(\d+(?:\s*,\s*\d+)*)", stripped_line)

                if not id_match:
                    results.append(stripped_line)
                    continue

                numbers_str = id_match.group(1)
                numbers = []
                try:
                    numbers = [int(n) for n in re.findall(r"\d+", numbers_str)]
                except ValueError:
                    logger.warning(f"无法解析行首数字，跳过行: {line}")
                    results.append(stripped_line)
                    continue

                if not numbers:
                    results.append(stripped_line)
                    continue

                final_comment_from_bot = query_item(numbers)
                id_string = ", ".join(map(str, numbers))

                output_line = f"{id_string} #{final_comment_from_bot}" if final_comment_from_bot else id_string
                results.append(output_line.strip())

            final_text = "\n".join(results)
            logger.info(f"处理完成，结果文本长度: {len(final_text)}")

    # 返回渲染后的模板
    return render_template('index.html', final_text=final_text, error_message=error_message)


# 这个路由在 Vercel 上将无法将文件保存到服务器的文件系统。
# 如果需要持久化保存，请集成外部存储服务（如数据库或云存储）。
@app.route('/save_config', methods=['POST'])
def save_config():
    logger.warning("尝试在 Vercel (无服务器环境) 上调用 '/save_config'。本地文件保存不被支持。")
    return jsonify({"success": False, "message": "服务器端文件保存功能在 Vercel 环境中不被支持。请考虑使用外部持久化存储。"}), 501


# Vercel 不会执行这里的 if __name__ == "__main__": 块
# 它会直接加载 app 实例。
# app.run() 仅用于本地开发测试。
# if __name__ == "__main__":
#     logger.info("本地开发模式: 开始运行 Flask Web 应用...")
#     # load_code_table() # 已经移到全局作用域以确保在Vercel上加载
#     app.run(host='0.0.0.0', port=5000, debug=True)
