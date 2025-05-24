from flask import Flask, render_template, request, jsonify
import os
# import json # json 模块在此文件中未直接使用，但保留以防未来需要
# import time # time 模块在此文件中未直接使用，但保留以防未来需要
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid
# import shutil # shutil 模块在此文件中未直接使用

# 导入自定义模块
from novel_processor import NovelProcessor
from narrative_engine import NarrativeEngine
import history_manager
import save_manager  # 虽然 save_manager.save_game_state 不再直接从app.py调用，但其他函数可能仍被使用
import config_manager
import utils
# from llm_client import LLMClient # <--- 不再使用这个旧的 LLMClient
from ollama_client import OllamaClient  # <--- 导入 OllamaClient
from generic_online_api_client import GenericOnlineAPIClient  # <--- 导入 GenericOnlineAPIClient

# from llm_client_interface import get_llm_client # 或者可以使用这个工厂方法，但直接导入更清晰

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 确保数据目录存在
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

# 应用状态
app_state = {}


# 初始化应用状态
def init_app_state():
    # 加载API配置
    api_config = config_manager.load_api_configs(DATA_DIR)

    app_state["use_online_api"] = api_config.get("use_online_api", False)
    app_state["ollama_api_url"] = api_config.get("ollama_api_url", "http://127.0.0.1:11434")
    # ollama_api_url_config 用于在UI的API配置部分显示，即使当前未使用Ollama
    app_state["ollama_api_url_config"] = api_config.get("ollama_api_url", "http://127.0.0.1:11434")
    app_state["selected_ollama_model"] = api_config.get("selected_ollama_model",
                                                        "gemma3:12b-it-q8_0")  # 旧版兼容，实际模型由 writing_custom_ollama_model 等决定
    app_state["online_api_url"] = api_config.get("online_api_url", "")
    app_state["online_api_model"] = api_config.get("online_api_model", "")  # 旧版兼容
    app_state["online_api_key"] = api_config.get("online_api_key", "")

    # 前端UI选择的模型类型 (e.g., "llama3", "custom")
    app_state["analysis_model_name"] = api_config.get("analysis_model_name",
                                                      "llama3")  # UI选择：llama3, mistral, qwen, custom
    app_state["analysis_custom_type"] = api_config.get("analysis_custom_type", "ollama")  # "ollama" or "online"
    app_state["analysis_custom_ollama_model"] = api_config.get("analysis_custom_ollama_model", "")  # 具体 ollama 模型
    app_state["analysis_custom_online_model"] = api_config.get("analysis_custom_online_model", "")  # 具体在线模型

    app_state["writing_model_name"] = api_config.get("writing_model_name", "llama3")
    app_state["writing_custom_type"] = api_config.get("writing_custom_type", "ollama")
    app_state["writing_custom_ollama_model"] = api_config.get("writing_custom_ollama_model", "")
    app_state["writing_custom_online_model"] = api_config.get("writing_custom_online_model", "")

    app_state["available_ollama_models"] = api_config.get("available_ollama_models",
                                                          ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0"])
    app_state["app_stage"] = "config_novel"  # 初始阶段
    app_state["is_resuming_flag"] = False  # 用于标记是否从历史/存档恢复

    app_state["novel_title"] = ""
    app_state["novel_excerpt"] = ""
    app_state["world_setting"] = ""
    app_state["character_info"] = None

    app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
    app_state["show_history_panel"] = True  # 此状态似乎未在前端JS中动态使用

    app_state["narrative_history_display"] = []  # 用于UI显示对话

    app_state["narrative_engine"] = None  # 当前活动的叙事引擎实例
    app_state["engine_state_to_load"] = None  # 从存档/历史加载的状态

    # 当前活动小说的相关路径
    app_state["novel_data_dir"] = ""
    app_state["chapters_dir"] = ""
    app_state["analysis_path"] = ""
    # UI显示路径，与实际路径一致 (这些字段主要用于UI展示，实际逻辑应依赖上面三个)
    app_state["novel_specific_data_dir_ui"] = ""
    app_state["chapters_data_path_ui"] = ""
    app_state["final_analysis_path_ui"] = ""

    # LLM 和叙事参数
    app_state["initial_context_chapters"] = api_config.get("initial_context_chapters", 3)
    app_state["window_before"] = api_config.get("window_before", 2)  # 叙事引擎内部使用
    app_state["window_after"] = api_config.get("window_after", 2)  # 叙事引擎内部使用
    app_state["narrative_window_chapter_before"] = api_config.get("window_before", 2)  # UI显示/配置项
    app_state["narrative_window_chapter_after"] = api_config.get("window_after", 2)  # UI显示/配置项
    app_state["divergence_threshold"] = api_config.get("divergence_threshold", 0.7)

    app_state["temperature"] = api_config.get("temperature", 0.7)
    app_state["top_p"] = api_config.get("top_p", 0.9)
    app_state["max_tokens"] = api_config.get("max_tokens", 65536)
    app_state["frequency_penalty"] = api_config.get("frequency_penalty", 0.0)
    app_state["presence_penalty"] = api_config.get("presence_penalty", 0.0)

    # UI 设置
    app_state["show_typing_animation"] = api_config.get("show_typing_animation", True)
    app_state["typing_speed"] = api_config.get("typing_speed", 50)
    app_state["enable_keyboard_shortcuts"] = api_config.get("enable_keyboard_shortcuts", True)

    # LLM 客户端实例 (分析和写作可能使用不同配置，但通常是同一个客户端类型)
    app_state["llm_client"] = None  # 主客户端，通常用于写作/叙事
    # app_state["analysis_llm_client"] = None # 如果需要独立分析客户端
    # app_state["writing_llm_client"] = None  # 主客户端的别名

    init_llm_client()  # 根据配置初始化客户端


def reset_for_new_journey():
    """重置应用状态以准备新的旅程，但保留API和部分UI配置。"""
    # 重新加载持久化的配置 (API, LLM参数, UI设置等)
    # init_app_state() # 这会从 api_config.json 重新加载所有配置

    # 或者，更细致地只重置与小说和叙事相关的状态
    api_config = config_manager.load_api_configs(DATA_DIR)  # 先加载配置

    # 清理特定于当前小说的状态
    app_state["app_stage"] = "config_novel"
    app_state["is_resuming_flag"] = False
    app_state["novel_title"] = ""
    app_state["novel_excerpt"] = ""
    app_state["world_setting"] = ""
    app_state["character_info"] = None
    app_state["narrative_history_display"] = []
    app_state["narrative_engine"] = None
    app_state["engine_state_to_load"] = None
    app_state["novel_data_dir"] = ""
    app_state["chapters_dir"] = ""
    app_state["analysis_path"] = ""
    app_state["novel_specific_data_dir_ui"] = ""
    app_state["chapters_data_path_ui"] = ""
    app_state["final_analysis_path_ui"] = ""

    # 保留从 api_config 加载的配置项 (如API URL, 模型选择, LLM参数, UI参数等)
    # init_app_state() 会重新执行这个加载，所以调用它更全面
    # 但为了避免完全重置可能由用户在UI上临时更改但未保存到api_config.json的项，
    # 这里可以考虑只重置上述列表中的项。
    # 然而，规范的做法是所有持久化配置都应通过 config_manager 管理。
    # 所以，重新调用 init_app_state() 是合理的，它会确保从磁盘加载最新配置。
    init_app_state()  # 这会确保API配置等被重新加载并重新初始化LLM客户端


def get_effective_model_name(model_choice_key: str, custom_type_key: str, custom_ollama_key: str,
                             custom_online_key: str, general_ollama_key: str, general_online_key: str,
                             use_online_api: bool) -> str:
    """辅助函数，根据UI选择确定实际使用的模型名称"""
    model_choice = app_state.get(model_choice_key)  # e.g., "llama3", "custom"

    if model_choice == "custom":
        custom_type = app_state.get(custom_type_key)  # "ollama" or "online"
        # 修改：优先尊重custom_type，而非依赖use_online_api
        if custom_type == "ollama":
            return app_state.get(custom_ollama_key) or app_state.get(general_ollama_key, "未指定Ollama模型")
        elif custom_type == "online":
            return app_state.get(custom_online_key) or app_state.get(general_online_key, "未指定在线模型")
        else:  # 未知类型，回退
            return app_state.get(general_ollama_key) if not use_online_api else app_state.get(general_online_key,
                                                                                              "模型不适用")
    else:  # 预设模型 (e.g., "llama3", "mistral", "qwen")
        # 对于预设模型，其名称本身就是模型标识符
        # 如果是Ollama，这个名字需要是Ollama认识的；如果是在线API，也需要是API认识的。
        # 这里的 model_choice (如 "llama3") 直接用作模型名。
        # 如果Ollama没有名为 "llama3" 的模型，而有 "llama3:8b"，则需要用户在自定义中指定。
        return model_choice


def init_llm_client():
    """根据当前配置初始化LLM客户端。"""
    app_state["llm_client"] = None
    current_config = config_manager.load_api_configs(DATA_DIR)  # 从持久化配置加载

    # 修改：优先根据writing_custom_type决定使用哪种客户端
    writing_custom_type = app_state.get("writing_custom_type", "ollama")
    use_online = current_config.get("use_online_api", False)
    
    # 如果写作模型类型是online，则强制使用在线API
    if writing_custom_type == "online":
        use_online = True
        # 同步更新app_state和配置
        app_state["use_online_api"] = True
        config_manager.update_api_config(DATA_DIR, {"use_online_api": True})

    # 以 "writing_model" (叙事模型) 的配置为准来初始化主 llm_client
    # 因为分析阶段的 NovelProcessor 也会接收这个 llm_client 实例，并可指定不同模型名
    effective_writing_model = get_effective_model_name(
        "writing_model_name",
        "writing_custom_type",
        "writing_custom_ollama_model",
        "writing_custom_online_model",
        "selected_ollama_model",  # 通用Ollama模型（旧字段，可能需要逐步淘汰）
        "online_api_model",  # 通用在线模型（旧字段，可能需要逐步淘汰）
        use_online
    )

    client_to_init = None
    if use_online:
        api_url = current_config.get("online_api_url")
        api_key = current_config.get("online_api_key")
        model_for_client = effective_writing_model  # 使用计算出的写作模型

        if api_url and api_key and model_for_client:
            try:
                client_to_init = GenericOnlineAPIClient(api_url=api_url, api_key=api_key,
                                                        default_model=model_for_client)
                print(f"已初始化 GenericOnlineAPIClient, 默认写作模型: {model_for_client}")
            except Exception as e:
                print(f"初始化 GenericOnlineAPIClient 错误: {e}")
        else:
            print("在线API凭据或写作模型未完全配置。")
    else:  # 使用Ollama
        api_url = current_config.get("ollama_api_url")
        model_for_client = effective_writing_model  # 使用计算出的写作模型

        if api_url and model_for_client:
            try:
                client_to_init = OllamaClient(api_url=api_url, default_model=model_for_client)
                print(f"已初始化 OllamaClient, 默认写作模型: {model_for_client}")
            except Exception as e:
                print(f"初始化 OllamaClient 错误: {e}")
        else:
            print("Ollama API URL 或写作模型未配置。")

    app_state["llm_client"] = client_to_init
    # app_state["analysis_llm_client"] = client_to_init # 如果分析和写作共用实例
    # app_state["writing_llm_client"] = client_to_init  # 别名

    if not client_to_init:
        print("LLM 客户端初始化失败。")


init_app_state()  # 程序启动时初始化


@app.route('/')
def index():
    # 每次访问主页时，确保 app_state 与最新的持久化配置同步某些项
    current_config = config_manager.load_api_configs(DATA_DIR)

    # 更新可能由其他途径修改的配置项 (例如API测试后更新了可用模型列表)
    app_state["available_ollama_models"] = current_config.get("available_ollama_models", [])
    app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)

    # 确保UI显示的API URL与配置一致
    app_state["ollama_api_url_config"] = current_config.get("ollama_api_url", "http://127.0.0.1:11434")
    app_state["online_api_url"] = current_config.get("online_api_url", "")
    # app_state["online_api_key"] = current_config.get("online_api_key", "") # 不直接传递到模板

    # 确保UI选择的模型名与配置一致 (这些是由用户在UI选择并保存到config的)
    for key in ["analysis_model_name", "analysis_custom_type", "analysis_custom_ollama_model",
                "analysis_custom_online_model",
                "writing_model_name", "writing_custom_type", "writing_custom_ollama_model",
                "writing_custom_online_model",
                "use_online_api", "selected_ollama_model", "online_api_model"]:
        if key in current_config:
            app_state[key] = current_config[key]

    # 更新前端主页卡片上显示的模型名称
    # 分析模型
    app_state["display_analysis_model_on_card"] = get_effective_model_name(
        "analysis_model_name", "analysis_custom_type",
        "analysis_custom_ollama_model", "analysis_custom_online_model",
        "selected_ollama_model", "online_api_model",
        app_state.get("use_online_api", False)  # 用当前的API选择
    ) or "N/A"
    # 写作模型
    app_state["display_writing_model_on_card"] = get_effective_model_name(
        "writing_model_name", "writing_custom_type",
        "writing_custom_ollama_model", "writing_custom_online_model",
        "selected_ollama_model", "online_api_model",
        app_state.get("use_online_api", False)
    ) or "N/A"

    # 如果客户端未初始化，也显示N/A
    if not app_state.get("llm_client"):
        app_state["display_analysis_model_on_card"] = "N/A (客户端未就绪)"
        app_state["display_writing_model_on_card"] = "N/A (客户端未就绪)"

    return render_template('index.html', app_state=app_state)


@app.route('/api/update_api_config', methods=['POST'])
def update_api_config_route():
    data = request.json
    updates_to_save = {}  # 存储需要保存到 config_manager 的更新

    # 写作模型选择 - 需要先处理这部分，因为它可能影响use_online_api
    for key in ["writing_model_name", "writing_custom_type", "writing_custom_ollama_model",
                "writing_custom_online_model"]:
        if key in data:
            updates_to_save[key] = data[key]
            app_state[key] = data[key]
            
    # 修改：当writing_custom_type为"online"时，自动设置use_online_api为True
    if data.get("writing_custom_type") == "online":
        updates_to_save["use_online_api"] = True
        app_state["use_online_api"] = True
    
    # 基本API类型选择
    if "use_online_api" in data:
        updates_to_save["use_online_api"] = data["use_online_api"]
        app_state["use_online_api"] = data["use_online_api"]  # 立即更新内存状态

    # Ollama 配置
    if "ollama_api_url" in data:
        updates_to_save["ollama_api_url"] = data["ollama_api_url"]
        app_state["ollama_api_url_config"] = data["ollama_api_url"]
        app_state["ollama_api_url"] = data["ollama_api_url"]

    # 在线API 配置
    if "online_api_url" in data:
        updates_to_save["online_api_url"] = data["online_api_url"]
        app_state["online_api_url"] = data["online_api_url"]
    if "online_api_key" in data:  # 密钥也保存到配置
        updates_to_save["online_api_key"] = data["online_api_key"]
        app_state["online_api_key"] = data["online_api_key"]

    # 通用模型名称 (这些是旧版UI字段，新版UI用custom选项)
    if "selected_ollama_model" in data:
        updates_to_save["selected_ollama_model"] = data["selected_ollama_model"]
        app_state["selected_ollama_model"] = data["selected_ollama_model"]
    if "online_api_model" in data:
        updates_to_save["online_api_model"] = data["online_api_model"]
        app_state["online_api_model"] = data["online_api_model"]

    # 分析模型选择
    for key in ["analysis_model_name", "analysis_custom_type", "analysis_custom_ollama_model",
                "analysis_custom_online_model"]:
        if key in data:
            updates_to_save[key] = data[key]
            app_state[key] = data[key]

    # 模型参数 (temperature, top_p, etc.)
    model_param_keys = ["temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty"]
    for key in model_param_keys:
        if key in data:
            updates_to_save[key] = data[key]
            app_state[key] = data[key]

    # 叙事窗口设置
    narrative_setting_keys = ["initial_context_chapters", "window_before", "window_after", "divergence_threshold"]
    for key in narrative_setting_keys:
        if key in data:
            updates_to_save[key] = data[key]
            app_state[key] = data[key]
            if key == "window_before": app_state["narrative_window_chapter_before"] = data[key]
            if key == "window_after": app_state["narrative_window_chapter_after"] = data[key]

    # UI 设置 (也保存到配置文件)
    ui_setting_keys = ["show_typing_animation", "typing_speed", "enable_keyboard_shortcuts"]
    for key in ui_setting_keys:
        if key in data:
            updates_to_save[key] = data[key]
            app_state[key] = data[key]

    if updates_to_save:
        config_manager.update_api_config(DATA_DIR, updates_to_save)

    init_llm_client()  # 应用新配置，重新初始化LLM客户端

    return jsonify({'success': True, 'message': 'API配置已更新'})


@app.route('/api/refresh_ollama_models', methods=['POST'])
def refresh_ollama_models():
    data = request.json
    # UI传入的api_url优先，否则用app_state中的ollama_api_url (已通过ollama_api_url_config更新)
    api_url = data.get('api_url', app_state.get("ollama_api_url"))

    if not api_url:
        return jsonify({'success': False, 'error': 'Ollama API URL不能为空'})
    try:
        # 用一个临时模型名创建客户端，因为我们只关心列出模型
        temp_client = OllamaClient(api_url=api_url, default_model="any_model_placeholder")
        models_data = temp_client.list_local_models()  # 返回的是 [{"name": "model1"}, ...]

        if models_data is not None:  # 可能返回空列表
            model_names = [m.get("name") for m in models_data if m.get("name")]
            app_state["available_ollama_models"] = model_names
            # 将获取到的模型列表也保存到配置文件中
            config_manager.update_api_config(DATA_DIR, {"available_ollama_models": model_names})
            return jsonify({'success': True, 'models': model_names})
        else:  # API调用成功但返回None或列表解析问题
            return jsonify({'success': False, 'error': '获取Ollama模型列表失败或列表为空 (API可能无响应或无模型)'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'获取Ollama模型列表时出错: {str(e)}'})


@app.route('/api/test_api', methods=['POST'])
def test_api():
    data = request.json
    test_message = data.get('message', '')

    if not test_message:
        return jsonify({'success': False, 'error': '测试消息不能为空'})

    if not app_state.get("llm_client"):  # 如果主客户端未初始化
        init_llm_client()  # 尝试根据当前保存的配置初始化
        if not app_state.get("llm_client"):
            return jsonify({'success': False, 'error': 'LLM客户端未能初始化，请检查API配置'})

    current_llm_client = app_state["llm_client"]
    # 获取当前为测试选择的LLM参数 (从内存中的app_state获取，这些已通过UI或配置加载)
    model_params_for_test = {
        "temperature": app_state.get("temperature", 0.7),
        "top_p": app_state.get("top_p", 0.9),
        "max_tokens": app_state.get("max_tokens", 1024),  # 测试时可以考虑用一个较小的值
        "frequency_penalty": app_state.get("frequency_penalty", 0.0),
        "presence_penalty": app_state.get("presence_penalty", 0.0),
    }

    # 测试时，我们应该使用当前为“写作”或“叙事”配置的那个模型
    # current_llm_client.default_model 已经是这个模型了
    test_model_name = current_llm_client.default_model
    print(f"测试API，使用模型: {test_model_name}，客户端类型: {current_llm_client.client_type}")

    try:
        response_data = current_llm_client.generate_chat_completion(
            model=test_model_name,
            messages=[
                {"role": "system", "content": "你是一个有用的AI助手。请简洁回答。"},
                {"role": "user", "content": test_message}
            ],
            options=model_params_for_test,
            timeout=30  # 测试时给一个合理的超时
        )
        if response_data and response_data.get("message") and response_data.get("message").get("content") is not None:
            return jsonify({'success': True, 'response': response_data["message"]["content"]})
        else:
            error_detail = f"API响应格式不符合预期: {response_data}" if response_data else "API未返回有效响应"
            return jsonify({'success': False, 'error': f'获取API响应失败。{error_detail}'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'测试API连接时出错: {str(e)}'})


@app.route('/upload_novel', methods=['POST'])
def upload_novel():
    if 'novel_file' not in request.files:
        return jsonify({'success': False, 'error': '没有找到文件'})
    file = request.files['novel_file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})
    if not file.filename.endswith('.txt'):
        return jsonify({'success': False, 'error': '只支持TXT格式的文件'})

    novel_title_from_form = request.form.get('novel_title', '')
    # 如果表单提供了标题则用表单的，否则用文件名（不含扩展名）
    novel_title = novel_title_from_form if novel_title_from_form.strip() else os.path.splitext(file.filename)[0]
    
    # 保存原始文件名，用于历史对话标题
    original_filename = file.filename
    app_state["original_filename"] = original_filename

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    # 清理标题用于目录名，如果标题为空则用默认名
    novel_base_name_for_dir = utils.sanitize_filename(novel_title if novel_title.strip() else "untitled_novel")
    per_novel_upload_dir_name = f"{timestamp}_{novel_base_name_for_dir}_{unique_id}"

    novel_data_dir = os.path.join(DATA_DIR, per_novel_upload_dir_name)
    os.makedirs(novel_data_dir, exist_ok=True)

    # 保存原始文件到这个小说专属目录
    file_path_in_data_dir = os.path.join(novel_data_dir, secure_filename(file.filename))
    file.seek(0)  # 确保从文件开头读取
    file.save(file_path_in_data_dir)

    app_state["app_stage"] = "processing"
    app_state["novel_title"] = novel_title  # 更新应用状态中的小说标题
    app_state["novel_data_dir"] = novel_data_dir
    app_state["chapters_dir"] = os.path.join(novel_data_dir, 'chapters')
    app_state["analysis_path"] = os.path.join(novel_data_dir, 'final_analysis.json')  # 小说分析结果的预期路径

    # 更新UI显示的路径
    app_state["novel_specific_data_dir_ui"] = novel_data_dir
    app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
    app_state["final_analysis_path_ui"] = app_state["analysis_path"]

    if not app_state.get("llm_client"):  # 确保主LLM客户端已初始化
        init_llm_client()
        if not app_state.get("llm_client"):
            app_state["app_stage"] = "config_novel"  # 回到配置阶段
            return jsonify({'success': False, 'error': 'LLM客户端初始化失败，请检查API配置后再上传。'})

    # 为 NovelProcessor 确定分析模型和客户端
    # 修改：根据analysis_custom_type动态选择客户端类型，确保与API类型匹配
    current_api_config_for_analysis = config_manager.load_api_configs(DATA_DIR)
    
    # 获取分析模型的类型和名称
    analysis_custom_type = app_state.get("analysis_custom_type", "ollama")
    analysis_model_name = app_state.get("analysis_model_name", "")
    
    # 根据分析模型类型决定使用哪种客户端
    analysis_client = None
    effective_analysis_model = ""
    
    if analysis_custom_type == "online":
        # 使用在线API客户端
        api_url = current_api_config_for_analysis.get("online_api_url", "")
        api_key = current_api_config_for_analysis.get("online_api_key", "")
        
        if analysis_model_name == "custom":
            effective_analysis_model = app_state.get("analysis_custom_online_model", "")
        else:
            effective_analysis_model = analysis_model_name
            
        if api_url and api_key and effective_analysis_model:
            try:
                analysis_client = GenericOnlineAPIClient(
                    api_url=api_url, 
                    api_key=api_key,
                    default_model=effective_analysis_model
                )
                print(f"已为分析阶段初始化 GenericOnlineAPIClient, 模型: {effective_analysis_model}")
            except Exception as e:
                print(f"初始化分析阶段 GenericOnlineAPIClient 错误: {e}")
        else:
            print("在线API凭据或分析模型未完全配置。")
    else:  # 默认使用Ollama
        api_url = current_api_config_for_analysis.get("ollama_api_url", "")
        
        if analysis_model_name == "custom":
            effective_analysis_model = app_state.get("analysis_custom_ollama_model", "")
        else:
            effective_analysis_model = analysis_model_name
            
        if api_url and effective_analysis_model:
            try:
                analysis_client = OllamaClient(
                    api_url=api_url, 
                    default_model=effective_analysis_model
                )
                print(f"已为分析阶段初始化 OllamaClient, 模型: {effective_analysis_model}")
            except Exception as e:
                print(f"初始化分析阶段 OllamaClient 错误: {e}")
        else:
            print("Ollama API URL 或分析模型未配置。")
    
    # 如果无法创建分析客户端，则使用主客户端（写作模型客户端）
    if not analysis_client:
        analysis_client = app_state["llm_client"]
        effective_analysis_model = get_effective_model_name(
            "analysis_model_name",
            "analysis_custom_type",
            "analysis_custom_ollama_model",
            "analysis_custom_online_model",
            "selected_ollama_model", "online_api_model",
            current_api_config_for_analysis.get("use_online_api", False)
        )
        print(f"警告：无法创建专用分析客户端，将使用主客户端。分析模型: {effective_analysis_model}")

    print(f"小说分析将使用模型: {effective_analysis_model}")
    if not effective_analysis_model or "未指定" in effective_analysis_model or "不适用" in effective_analysis_model:
        app_state["app_stage"] = "config_novel"
        return jsonify(
            {'success': False, 'error': f'未能确定有效的分析模型: {effective_analysis_model}。请检查API和模型配置。'})

    # 传递分析客户端和模型名给 NovelProcessor
    novel_processor = NovelProcessor(
        llm_client=analysis_client,  # 使用专用的分析客户端
        novel_file_path=file_path_in_data_dir,
        output_dir=novel_data_dir,
        analysis_model_override=effective_analysis_model
    )

    success = novel_processor.process_novel()  # process_novel 内部应使用 effective_analysis_model

    if success:
        final_analysis = utils.read_json_file(app_state["analysis_path"])
        if final_analysis:
            app_state["app_stage"] = "initializing_narrative"  # 进入下一阶段
            app_state["novel_title"] = final_analysis.get("title", novel_title)  # 确保标题来自分析结果
            # 更新UI显示内容
            if "excerpts" in final_analysis and final_analysis["excerpts"]:
                app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "暂无精选片段")
            else:
                app_state["novel_excerpt"] = "分析完成，但未找到精选片段。"

            if "world_building" in final_analysis and final_analysis["world_building"]:
                wb_texts = [f"{item.get('name', '')}: {item.get('description', '')}" for item in
                            final_analysis["world_building"] if item.get('description')]  # 只显示有描述的
                app_state["world_setting"] = "\n".join(wb_texts) if wb_texts else "暂无世界设定信息"
            else:
                app_state["world_setting"] = "分析完成，但未找到世界设定信息。"

            if "characters" in final_analysis and final_analysis["characters"]:
                app_state["character_info"] = {
                    "name": final_analysis["characters"][0].get("name", "未知角色"),
                    "description": final_analysis["characters"][0].get("description", "暂无描述")
                }
            else:
                app_state["character_info"] = {"name": "未知角色", "description": "分析完成，但未找到人物信息。"}

            return jsonify({'success': True})
        else:
            app_state["app_stage"] = "config_novel"
            return jsonify({'success': False, 'error': '小说分析成功但加载分析结果失败'})
    else:
        app_state["app_stage"] = "config_novel"
        error_detail = app_state.get("llm_client").last_error if app_state.get("llm_client") and hasattr(
            app_state.get("llm_client"), "last_error") else "未知分析错误"
        if hasattr(novel_processor, 'last_error_detail') and novel_processor.last_error_detail:  # 假设processor记录错误
            error_detail = novel_processor.last_error_detail
        return jsonify({'success': False, 'error': f'处理小说失败，请检查后台日志。错误详情: {error_detail}'})


@app.route('/start_narrative', methods=['POST'])
def start_narrative():
    is_resuming_session = app_state.pop("is_resuming_flag", False)  # 获取并移除标记
    current_stage = app_state.get("app_stage")

    # 允许从 initializing_narrative (新开始) 或 resuming_narrative (从历史加载后) 进入
    if current_stage not in ["initializing_narrative", "resuming_narrative"]:
        return jsonify(
            {'success': False, 'error': f'应用状态不正确 ({current_stage})，无法开始/恢复叙事。'})

    if not app_state.get("llm_client"):  # 主客户端 (写作模型客户端)
        init_llm_client()
        if not app_state.get("llm_client"):
            return jsonify({'success': False, 'error': 'LLM客户端初始化失败，无法开始叙事。'})

    # 加载最新的LLM参数等配置
    current_api_config = config_manager.load_api_configs(DATA_DIR)
    model_params = config_manager.get_model_params(current_api_config)

    # NarrativeEngine 使用的 model_name 应该是写作模型的名称。
    # app_state["llm_client"] 的 default_model 已经根据写作模型配置初始化。
    writing_model_for_engine = app_state["llm_client"].default_model

    app_state["narrative_engine"] = NarrativeEngine(
        llm_client=app_state["llm_client"],
        novel_data_dir=app_state["novel_data_dir"],
        chapters_dir=app_state["chapters_dir"],
        analysis_path=app_state["analysis_path"],
        model_name=writing_model_for_engine,  # 引擎记录它被初始化时使用的模型
        saved_state=app_state.get("engine_state_to_load")  # 如果是加载，这里会有状态
    )
    app_state["engine_state_to_load"] = None  # 用完后清除

    initial_or_resumed_narrative = app_state["narrative_engine"].initialize_narrative_session(
        initial_context_chapters=current_api_config.get("initial_context_chapters", 3),
        window_before=current_api_config.get("window_before", 2),  # UI上叫 narrative_window_chapter_before
        window_after=current_api_config.get("window_after", 2),  # UI上叫 narrative_window_chapter_after
        divergence_threshold=current_api_config.get("divergence_threshold", 0.7),
        model_params=model_params,
        is_resuming=is_resuming_session  # 传递恢复标记
    )

    if initial_or_resumed_narrative is not None:
        app_state["app_stage"] = "narrating"  # 统一进入叙事阶段
        app_state["narrative_history_display"] = []  # 重新构建UI显示的历史

        # 从引擎的 conversation_history 构建UI显示历史
        # 这个 history 此时要么是新初始化的，要么是从存档加载的
        if hasattr(app_state["narrative_engine"], 'conversation_history'):
            for entry in app_state["narrative_engine"].conversation_history:
                speaker = "用户" if entry.get("role") == "user" else ("系统" if entry.get("role") == "system" else "AI")
                app_state["narrative_history_display"].append((speaker, entry.get("content", "")))

        return jsonify({'success': True, 'initial_narrative': initial_or_resumed_narrative})
    else:
        error_msg = "初始化/恢复叙事会话失败。"
        if hasattr(app_state["narrative_engine"], 'last_error') and app_state["narrative_engine"].last_error:
            error_msg += f" 详情: {app_state['narrative_engine'].last_error}"

        # 如果失败，尝试恢复到合适的阶段
        if is_resuming_session:
            app_state["app_stage"] = "config_novel"  # 或显示错误页，让用户重新加载或配置
        else:  # 如果是全新初始化失败
            app_state["app_stage"] = "initializing_narrative"  # 允许用户重试"开始旅程"
            # 或者退回 config_novel 让用户检查配置
        app_state["narrative_engine"] = None  # 清理失败的引擎实例
        return jsonify({'success': False, 'error': error_msg})


@app.route('/process_action', methods=['POST'])
def process_action():
    data = request.json
    user_action = data.get('action', '')
    if not user_action:
        return jsonify({'success': False, 'error': '用户行动不能为空'})
    if app_state.get("app_stage") != "narrating" or not app_state.get("narrative_engine"):
        return jsonify({'success': False, 'error': '应用状态不正确或叙事引擎未初始化'})

    current_api_config = config_manager.load_api_configs(DATA_DIR)
    model_params = config_manager.get_model_params(current_api_config)

    response = app_state["narrative_engine"].process_user_action(user_action, model_params)

    if response is not None:
        app_state["narrative_history_display"] = []  # 重新构建UI显示
        if hasattr(app_state["narrative_engine"], 'conversation_history'):
            for entry in app_state["narrative_engine"].conversation_history:
                speaker = "用户" if entry.get("role") == "user" else ("系统" if entry.get("role") == "system" else "AI")
                app_state["narrative_history_display"].append((speaker, entry.get("content", "")))
        
        # 自动保存对话到历史记录
        # 准备用于历史记录的配置快照
        app_config_for_history = {key: current_api_config.get(key) for key in [
            "temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty",
            "initial_context_chapters", "window_before", "window_after", "divergence_threshold",
            "use_online_api",
            "analysis_model_name", "analysis_custom_type", "analysis_custom_ollama_model",
            "analysis_custom_online_model",
            "writing_model_name", "writing_custom_type", "writing_custom_ollama_model", "writing_custom_online_model",
            "selected_ollama_model", "online_api_model"
        ]}
        # 补全 ollama_api_url 和 online_api_url (但不包括 key)
        app_config_for_history["ollama_api_url"] = current_api_config.get("ollama_api_url")
        app_config_for_history["online_api_url"] = current_api_config.get("online_api_url")

        # 获取原始文件名作为历史对话标题
        original_filename = app_state.get("original_filename", None)
        
        # 自动保存到历史记录
        history_path = history_manager.save_current_conversation(
            data_dir=DATA_DIR,
            narrative_engine=app_state["narrative_engine"],
            novel_name=app_state.get("novel_title", "未知小说"),
            app_config=app_config_for_history,
            original_filename=original_filename
        )
        
        # 刷新历史对话列表
        if history_path:
            app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
            
        return jsonify({'success': True, 'response': response})
    else:
        error_msg = "处理用户行动失败。"
        if hasattr(app_state["narrative_engine"], 'last_error') and app_state["narrative_engine"].last_error:
            error_msg += f" 详情: {app_state['narrative_engine'].last_error}"
        return jsonify({'success': False, 'error': error_msg})


@app.route('/save_game', methods=['POST'])
def save_game():
    if app_state.get("app_stage") != "narrating" or not app_state.get("narrative_engine"):
        return jsonify({'success': False, 'error': '应用状态不正确或叙事引擎未初始化，无法保存'})

    save_path = app_state["narrative_engine"].save_state_to_file()

    if save_path:
        current_api_config = config_manager.load_api_configs(DATA_DIR)
        # 准备用于历史记录的配置快照
        app_config_for_history = {key: current_api_config.get(key) for key in [
            "temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty",
            "initial_context_chapters", "window_before", "window_after", "divergence_threshold",
            "use_online_api",
            # 保存实际选择的模型名称，而不是类别名
            "analysis_model_name", "analysis_custom_type", "analysis_custom_ollama_model",
            "analysis_custom_online_model",
            "writing_model_name", "writing_custom_type", "writing_custom_ollama_model", "writing_custom_online_model",
            # 也保存旧的通用模型字段，以防万一
            "selected_ollama_model", "online_api_model"
        ]}
        # 补全 ollama_api_url 和 online_api_url (但不包括 key)
        app_config_for_history["ollama_api_url"] = current_api_config.get("ollama_api_url")
        app_config_for_history["online_api_url"] = current_api_config.get("online_api_url")

        history_path = history_manager.save_current_conversation(
            data_dir=DATA_DIR,
            narrative_engine=app_state["narrative_engine"],
            novel_name=app_state.get("novel_title", "未知小说"),
            app_config=app_config_for_history  # 传递配置快照
        )

        if history_path:
            app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
            return jsonify({'success': True, 'save_path': save_path, 'history_path': history_path,
                            'message': '游戏已保存，并已创建历史对话记录！'})
        else:
            return jsonify({'success': True, 'save_path': save_path, 'history_path': None,
                            'message': '游戏已保存，但创建历史对话记录失败。'})
    else:
        error_msg = '保存游戏状态失败。'
        if hasattr(app_state["narrative_engine"], 'last_error') and app_state["narrative_engine"].last_error:
            error_msg += f"详情: {app_state['narrative_engine'].last_error}"
        return jsonify({'success': False, 'error': error_msg})


@app.route('/load_game', methods=['POST'])
def load_game():  # 从游戏存档（非历史记录）加载
    data = request.json
    save_path = data.get('save_path', '')

    if not save_path or not os.path.exists(save_path):
        return jsonify({'success': False, 'error': '存档路径无效或文件不存在'})

    loaded_state_from_save_file = utils.read_json_file(save_path)

    if loaded_state_from_save_file:
        app_state["engine_state_to_load"] = loaded_state_from_save_file

        # 从存档数据中恢复关键路径信息到 app_state
        app_state["novel_data_dir"] = loaded_state_from_save_file.get("novel_data_dir", "")
        app_state["chapters_dir"] = loaded_state_from_save_file.get("chapters_dir", "")
        app_state["analysis_path"] = loaded_state_from_save_file.get("analysis_path", "")

        # 更新UI路径
        app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
        app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
        app_state["final_analysis_path_ui"] = app_state["analysis_path"]

        # 尝试加载并显示小说基本信息 (从分析文件)
        if app_state["analysis_path"] and os.path.exists(app_state["analysis_path"]):
            final_analysis = utils.read_json_file(app_state["analysis_path"])
            if final_analysis:
                app_state["novel_title"] = final_analysis.get("title", "未知小说")
                # ... (省略更新 excerpt, world_setting, character_info 的重复代码，与 upload_novel 中逻辑类似)
                if "excerpts" in final_analysis and final_analysis["excerpts"]:
                    app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "")
                if "world_building" in final_analysis and final_analysis["world_building"]:
                    wb_texts = [f"{item.get('name', '')}: {item.get('description', '')}" for item in
                                final_analysis["world_building"] if item.get('description')]
                    app_state["world_setting"] = "\n".join(wb_texts) if wb_texts else ""
                if "characters" in final_analysis and final_analysis["characters"]:
                    app_state["character_info"] = final_analysis["characters"][0]
        elif "novel_data_dir" in loaded_state_from_save_file:  # 尝试从存档的 novel_data_dir 推断标题
            base_dir_name = os.path.basename(loaded_state_from_save_file["novel_data_dir"])
            parts = base_dir_name.split('_')
            if len(parts) > 1 and parts[0].isdigit():  # 检查是否是 YYYYMMDDHHMMSS_title_uuid 格式
                app_state["novel_title"] = parts[1] if len(parts) > 2 else parts[0]  # 简单提取

        # 从存档中恢复模型名称 (如果存在)，并尝试设置API配置
        # 注意：存档通常不包含完整的API key等敏感信息，所以这里的恢复是有限的。
        # 更好的做法是让用户在加载后确认或调整API配置。
        # 这里我们只尝试恢复模型名，API类型等由用户当前的全局配置决定。
        saved_model_name = loaded_state_from_save_file.get("model_name")
        if saved_model_name:
            # 这是一个简化的恢复：假设用户当前的API类型 (Ollama/Online) 适合这个模型
            # 并且这个模型名在当前API类型下是有效的。
            # 更鲁棒的做法是存档中也保存API类型，并在加载时验证。
            # app_state["writing_model_name"] = saved_model_name # 这会影响 get_effective_model_name
            # init_llm_client() # 根据潜在更新的模型名重新初始化客户端
            print(f"存档中记录的模型为: {saved_model_name}。请确保当前API配置支持此模型。")

        app_state["app_stage"] = "resuming_narrative"  # 改为恢复阶段
        app_state["is_resuming_flag"] = True  # 设置恢复标记
        return jsonify({'success': True, 'message': '游戏存档已加载，准备继续旅程。'})
    else:
        return jsonify({'success': False, 'error': '加载游戏状态失败'})


@app.route('/api/saves/list', methods=['GET'])
def get_saves_list_route():
    # novel_data_dir 可能在加载历史或存档后才设置
    current_novel_data_dir = app_state.get("novel_data_dir")
    if not current_novel_data_dir or not os.path.exists(current_novel_data_dir):
        return jsonify({'success': True, 'saves': [], 'message': '当前无激活小说，或小说数据目录无效，无法列出存档。'})
    saves = save_manager.get_saves_list(current_novel_data_dir)
    return jsonify({'success': True, 'saves': saves})


@app.route('/api/history/list', methods=['GET'])
def get_history_list_route():
    history_list = history_manager.load_history_conversations(DATA_DIR)
    app_state["history_conversations"] = history_list  # 更新内存中的列表
    return jsonify({'success': True, 'history': history_list})


@app.route('/api/history/save', methods=['POST'])  # 手动保存当前对话到历史
def save_history_route():
    if app_state.get("app_stage") != "narrating" or not app_state.get("narrative_engine"):
        return jsonify({'success': False, 'error': '当前无正在进行的叙事，无法保存到历史。'})

    current_api_config = config_manager.load_api_configs(DATA_DIR)
    app_config_for_history = {key: current_api_config.get(key) for key in [
        "temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty",
        "initial_context_chapters", "window_before", "window_after", "divergence_threshold",
        "use_online_api",
        "analysis_model_name", "analysis_custom_type", "analysis_custom_ollama_model", "analysis_custom_online_model",
        "writing_model_name", "writing_custom_type", "writing_custom_ollama_model", "writing_custom_online_model",
        "selected_ollama_model", "online_api_model"
    ]}
    app_config_for_history["ollama_api_url"] = current_api_config.get("ollama_api_url")
    app_config_for_history["online_api_url"] = current_api_config.get("online_api_url")

    history_path = history_manager.save_current_conversation(
        data_dir=DATA_DIR,
        narrative_engine=app_state["narrative_engine"],
        novel_name=app_state.get("novel_title", "未知小说"),
        app_config=app_config_for_history
    )
    if history_path:
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)  # 刷新列表
        return jsonify({'success': True, 'history_path': history_path, 'message': '当前对话已保存到历史记录。'})
    else:
        return jsonify({'success': False, 'error': '保存历史对话失败'})


@app.route('/api/history/delete', methods=['POST'])
def delete_history_route():
    data = request.json
    file_path = data.get('file_path', '')
    if not file_path:
        return jsonify({'success': False, 'error': '未提供文件路径'})

    # 安全性：再次确认路径在预期的 history 目录内
    # (虽然 history_manager.load_history_conversations 已返回合法路径，但多一层检查无妨)
    history_base_dir = os.path.join(DATA_DIR, history_manager.HISTORY_DIR)
    if not os.path.normpath(file_path).startswith(os.path.normpath(history_base_dir)):
        return jsonify({'success': False, 'error': '提供的历史文件路径不安全。'})
    if not os.path.exists(file_path):  # 再次检查文件是否存在
        return jsonify({'success': False, 'error': '历史文件不存在。'})

    success = history_manager.delete_history_conversation(file_path)
    if success:
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)  # 刷新
        return jsonify({'success': True, 'message': '历史对话已删除。'})
    else:
        return jsonify({'success': False, 'error': '删除历史对话失败'})


@app.route('/api/history/load', methods=['POST'])
def load_history_route():  # 从历史记录加载
    data = request.json
    file_path = data.get('file_path', '')
    direct_to_narrative = data.get('direct_to_narrative', False)  # 新增参数，控制是否直接进入故事页面
    
    if not file_path or not os.path.exists(file_path):
        return jsonify({'success': False, 'error': '历史对话文件路径无效或文件不存在。'})
    try:
        history_item_data = utils.read_json_file(file_path)
        if not history_item_data:
            return jsonify({'success': False, 'error': '加载历史对话数据失败或文件为空。'})

        result = history_manager.load_conversation_from_history(history_item_data)

        if result.get("success"):
            loaded_app_config = result.get("app_config", {})
            engine_state_to_load = result.get("engine_state")

            # 更新全局配置 (api_config.json) 和内存中的 app_state
            config_updates_for_file = {}
            default_config_keys = config_manager.load_api_configs(DATA_DIR).keys()  # 获取标准配置项

            for key, value in loaded_app_config.items():
                if key in default_config_keys:  # 只更新标准配置项
                    app_state[key] = value
                    config_updates_for_file[key] = value

            # 特殊处理UI相关的 window_before/after
            if "window_before" in loaded_app_config:
                app_state["narrative_window_chapter_before"] = loaded_app_config["window_before"]
            if "window_after" in loaded_app_config:
                app_state["narrative_window_chapter_after"] = loaded_app_config["window_after"]

            if config_updates_for_file:
                config_manager.update_api_config(DATA_DIR, config_updates_for_file)

            init_llm_client()  # 根据加载的配置重新初始化LLM客户端
            if not app_state.get("llm_client"):
                return jsonify({'success': False, 'error': '根据历史记录配置LLM客户端失败。请检查API设置。'})

            app_state["engine_state_to_load"] = engine_state_to_load  # 这个状态会被 NarrativeEngine.__init__ 使用

            if engine_state_to_load:  # 从引擎状态恢复小说特定路径
                app_state["novel_data_dir"] = engine_state_to_load.get("novel_data_dir", "")
                app_state["chapters_dir"] = engine_state_to_load.get("chapters_dir", "")
                app_state["analysis_path"] = engine_state_to_load.get("analysis_path", "")
                # 更新UI路径
                app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
                app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
                app_state["final_analysis_path_ui"] = app_state["analysis_path"]

                # 加载小说基本信息用于UI显示
                if app_state["analysis_path"] and os.path.exists(app_state["analysis_path"]):
                    final_analysis = utils.read_json_file(app_state["analysis_path"])
                    if final_analysis:
                        app_state["novel_title"] = final_analysis.get("title", "未知小说")
                        # ... (省略更新 excerpt, world_setting, character_info 的重复代码)
                        if "excerpts" in final_analysis and final_analysis["excerpts"]:
                            app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "")
                        if "world_building" in final_analysis and final_analysis["world_building"]:
                            wb_texts = [f"{item.get('name', '')}: {item.get('description', '')}" for item in
                                        final_analysis["world_building"] if item.get('description')]
                            app_state["world_setting"] = "\n".join(wb_texts) if wb_texts else ""
                        if "characters" in final_analysis and final_analysis["characters"]:
                            app_state["character_info"] = final_analysis["characters"][0]
                elif history_item_data.get("metadata", {}).get("novel_name"):  # 如果分析文件找不到，尝试从历史元数据获取
                    app_state["novel_title"] = history_item_data["metadata"]["novel_name"]
            else:  # 如果历史记录中没有引擎状态 (不太可能，但做防御)
                app_state["engine_state_to_load"] = None

            # 设置正确的应用阶段和恢复标记
            if app_state["engine_state_to_load"] and app_state["engine_state_to_load"].get("session_memory"):
                app_state["app_stage"] = "resuming_narrative"
                app_state["is_resuming_flag"] = True
                print("App stage set to resuming_narrative from history load.")
                
                # 如果请求直接进入故事页面，则初始化叙事引擎并返回对话历史
                if direct_to_narrative:
                    # 初始化叙事引擎
                    app_state["narrative_engine"] = NarrativeEngine(
                        llm_client=app_state["llm_client"],
                        novel_data_dir=app_state["novel_data_dir"],
                        chapters_dir=app_state["chapters_dir"],
                        analysis_path=app_state["analysis_path"],
                        model_name=app_state["llm_client"].default_model,
                        saved_state=app_state["engine_state_to_load"]
                    )
                    
                    # 设置应用状态为叙事中
                    app_state["app_stage"] = "narrating"
                    
                    # 构建UI显示的历史对话
                    app_state["narrative_history_display"] = []
                    if hasattr(app_state["narrative_engine"], 'conversation_history'):
                        for entry in app_state["narrative_engine"].conversation_history:
                            speaker = "用户" if entry.get("role") == "user" else ("系统" if entry.get("role") == "system" else "AI")
                            app_state["narrative_history_display"].append((speaker, entry.get("content", "")))
                    
                    # 返回对话历史以便前端直接渲染
                    return jsonify({
                        'success': True, 
                        'direct_narrative': True,
                        'conversation_history': app_state["narrative_history_display"],
                        'message': '历史对话已加载，已直接进入故事页面。'
                    })
            else:  # 没有有效引擎状态可恢复，则回到新小说配置阶段
                app_state["app_stage"] = "config_novel"  # 或者 initializing_narrative 如果小说信息已加载
                app_state["is_resuming_flag"] = False
                print("No valid engine state in history to resume, app stage set to config_novel.")

            return jsonify({'success': True, 'message': '历史对话已加载，小说信息和配置已更新，准备继续旅程。'})
        else:
            return jsonify({'success': False, 'error': result.get("error", "从历史记录提取对话数据失败。")})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'加载历史对话时发生意外错误: {str(e)}'})


@app.route('/api/config/reset', methods=['POST'])
def reset_config_route():
    default_config = config_manager.reset_api_config(DATA_DIR)  # 重置配置文件到默认
    # 更新内存中的 app_state 以匹配默认配置
    for key, value in default_config.items():
        if key in app_state:  # 只更新 app_state 中存在的键
            app_state[key] = value

    # 特殊处理UI相关的 window_before/after
    app_state["narrative_window_chapter_before"] = default_config.get("window_before", 2)
    app_state["narrative_window_chapter_after"] = default_config.get("window_after", 2)

    init_llm_client()  # 根据重置后的配置重新初始化LLM客户端
    return jsonify({'success': True, 'message': 'API及应用配置已重置为默认值。'})


@app.route('/update_settings', methods=['POST'])  # 处理“设置”页面的保存
def update_settings_route():
    data = request.json
    updates_for_config_file = {}  # 需要持久化到 api_config.json 的设置

    # UI 显示相关的设置
    ui_setting_keys = ["show_typing_animation", "typing_speed", "enable_keyboard_shortcuts"]
    for key in ui_setting_keys:
        if key in data:
            app_state[key] = data[key]
            updates_for_config_file[key] = data[key]

    # LLM 模型参数
    model_param_keys = ["temperature", "top_p", "max_tokens"]  # frequency_penalty, presence_penalty 似乎不在设置页面
    for key in model_param_keys:
        if key in data:
            # 对数值进行类型转换和校验
            try:
                if key == "temperature" or key == "top_p":
                    value = float(data[key])
                elif key == "max_tokens":
                    value = int(data[key])
                else:
                    value = data[key]  # 其他参数保持原样

                app_state[key] = value
                updates_for_config_file[key] = value
            except ValueError:
                print(f"警告: 更新设置时，参数 {key} 的值 {data[key]} 类型无效。")

    # 叙事引擎相关的参数 (如果这些也在“设置”页面调整的话)
    # 当前这些参数似乎是在 API 配置中，但如果移到设置页，则在此处处理
    # narrative_setting_keys = ["initial_context_chapters", "window_before", "window_after", "divergence_threshold"]
    # for key in narrative_setting_keys:
    #     if key in data:
    #         app_state[key] = data[key]
    #         updates_for_config_file[key] = data[key]
    #         if key == "window_before": app_state["narrative_window_chapter_before"] = data[key]
    #         if key == "window_after": app_state["narrative_window_chapter_after"] = data[key]

    if updates_for_config_file:
        config_manager.update_api_config(DATA_DIR, updates_for_config_file)
        # 如果更新了影响LLM客户端的参数（如temperature），
        # 当前的LLM客户端在generate_chat_completion时会接收options参数，所以不一定需要重初始化。
        # 但如果LLM客户端缓存了这些参数，则可能需要。
        # init_llm_client()

    return jsonify({'success': True, 'message': '设置已更新。'})


@app.route('/reset_journey', methods=['POST'])  # “重置应用”按钮
def reset_journey_route():
    reset_for_new_journey()  # 这个函数会重置小说相关状态，并从磁盘重新加载配置
    return jsonify({'success': True, 'message': '应用已重置，可以开始新的旅程。'})


if __name__ == '__main__':
    # Gunicorn 等生产环境服务器通常有自己的日志配置，debug=True主要用于开发
    is_debug_env = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=is_debug_env, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))