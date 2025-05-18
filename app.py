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
import save_manager
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
    app_state["ollama_api_url_config"] = api_config.get("ollama_api_url", "http://127.0.0.1:11434")
    app_state["selected_ollama_model"] = api_config.get("selected_ollama_model",
                                                        "gemma3:12b-it-q8_0")  # 请确保这是您Ollama中存在的模型
    app_state["online_api_url"] = api_config.get("online_api_url", "")
    app_state["online_api_model"] = api_config.get("online_api_model", "")
    app_state["online_api_key"] = api_config.get("online_api_key", "")
    app_state["analysis_model_name"] = api_config.get("analysis_model_name", "llama3")  # 这似乎是预设模型类型，实际模型名取决于API配置
    app_state["writing_model_name"] = api_config.get("writing_model_name", "llama3")  # 同上

    # 为了兼容前端显示，这里从 api_config 中获取 available_ollama_models
    # 实际的 available_ollama_models 应该通过 refresh_ollama_models 动态获取并更新到 api_config.json 和 app_state
    app_state["available_ollama_models"] = api_config.get("available_ollama_models",
                                                          ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0"])

    # 应用阶段
    app_state["app_stage"] = "config_novel"  # config_novel, processing, initializing_narrative, narrating

    # 小说数据
    app_state["novel_title"] = ""
    app_state["novel_excerpt"] = ""
    app_state["world_setting"] = ""
    app_state["character_info"] = None

    # 历史对话
    app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)  # 初始化时加载历史记录
    app_state["show_history_panel"] = True

    # 叙事历史
    # app_state["narrative_history"] = [] # narrative_engine 会管理自己的历史
    app_state["narrative_history_display"] = []

    # 叙事引擎
    app_state["narrative_engine"] = None
    app_state["engine_state_to_load"] = None

    # 小说分析路径
    app_state["novel_data_dir"] = ""
    app_state["chapters_dir"] = ""
    app_state["analysis_path"] = ""
    app_state["novel_specific_data_dir_ui"] = ""
    app_state["chapters_data_path_ui"] = ""
    app_state["final_analysis_path_ui"] = ""

    # 叙事窗口设置
    app_state["initial_context_chapters"] = api_config.get("initial_context_chapters", 3)
    app_state["window_before"] = api_config.get("window_before", 2)
    app_state["window_after"] = api_config.get("window_after", 2)
    app_state["narrative_window_chapter_before"] = api_config.get("window_before", 2)
    app_state["narrative_window_chapter_after"] = api_config.get("window_after", 2)
    app_state["divergence_threshold"] = api_config.get("divergence_threshold", 0.7)

    # 模型参数
    app_state["temperature"] = api_config.get("temperature", 0.7)
    app_state["top_p"] = api_config.get("top_p", 0.9)
    app_state["max_tokens"] = api_config.get("max_tokens", 1024)
    app_state["frequency_penalty"] = api_config.get("frequency_penalty", 0.0)
    app_state["presence_penalty"] = api_config.get("presence_penalty", 0.0)

    # UI设置
    app_state["show_typing_animation"] = True  # 默认值，可以从配置加载
    app_state["typing_speed"] = 50  # 默认值
    app_state["enable_keyboard_shortcuts"] = True  # 默认值

    # LLM客户端
    app_state["llm_client"] = None  # 将在 init_llm_client 中初始化
    app_state["analysis_llm_client"] = None  # 兼容前端，实际指向 llm_client
    app_state["writing_llm_client"] = None  # 兼容前端，实际指向 llm_client

    init_llm_client()  # 初始化时就尝试创建LLM客户端


# 重置应用状态以准备新的旅程
def reset_for_new_journey():
    # 保留API配置和UI设置
    api_config_keys_to_keep = [
        "use_online_api", "ollama_api_url", "selected_ollama_model",
        "online_api_url", "online_api_model", "online_api_key",
        "analysis_model_name", "writing_model_name", "available_ollama_models",
        "temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty",
        "initial_context_chapters", "window_before", "window_after", "divergence_threshold"
    ]
    kept_api_config = {key: app_state.get(key) for key in api_config_keys_to_keep if app_state.get(key) is not None}

    ui_settings_keys_to_keep = [
        "show_typing_animation", "typing_speed", "enable_keyboard_shortcuts"
    ]
    kept_ui_settings = {key: app_state.get(key) for key in ui_settings_keys_to_keep if app_state.get(key) is not None}

    # 重新初始化应用状态 (会加载默认或已保存的配置)
    init_app_state()  # 这会重新加载 api_config.json

    # 确保保留的配置（如果用户在UI中更改了但未保存到api_config.json的）能够覆盖
    # 但通常这些应该已经通过 /api/update_api_config 保存到 api_config.json 了
    # 如果 reset_for_new_journey 是为了清除当前会话状态而非配置，那么 init_app_state() 应该足够

    # 如果希望保留UI中临时更改的配置（即使未保存到json），则需要下面逻辑：
    # for key, value in kept_api_config.items():
    #     if key in app_state and value is not None: # 确保不将None值写回
    #         app_state[key] = value

    # for key, value in kept_ui_settings.items():
    #     if key in app_state and value is not None:
    #         app_state[key] = value

    # 确保LLM客户端基于最新的（可能被保留的）配置重新初始化
    init_llm_client()


# 初始化LLM客户端
def init_llm_client():
    # 清理旧的客户端实例（如果存在）
    app_state["llm_client"] = None
    app_state["analysis_llm_client"] = None
    app_state["writing_llm_client"] = None

    current_config = config_manager.load_api_configs(DATA_DIR)  # 确保使用最新的持久化配置

    use_online = current_config.get("use_online_api", False)
    ollama_url = current_config.get("ollama_api_url")
    ollama_model = current_config.get("selected_ollama_model")  # 这个是分析和写作共用的基础模型名

    # 处理分析模型的选择逻辑
    # analysis_model_config_name 是指预设名如 "llama3", "mistral", "qwen", "custom"
    # 实际使用的模型名需要根据 API 类型和自定义设置来确定
    actual_analysis_model_name = ollama_model  # 默认使用 ollama_model

    if use_online:
        online_url = current_config.get("online_api_url")
        online_key = current_config.get("online_api_key")
        online_model_name = current_config.get("online_api_model")  # 这个是用户在在线API部分指定的模型名
        actual_analysis_model_name = online_model_name  # 如果是在线API，则使用这个

        if online_url and online_key and online_model_name:
            try:
                app_state["llm_client"] = GenericOnlineAPIClient(
                    api_url=online_url,
                    api_key=online_key,
                    default_model=online_model_name  # 使用在线API配置中的模型名
                )
                print(f"Initialized GenericOnlineAPIClient with model: {online_model_name}")
            except Exception as e:
                print(f"Error initializing GenericOnlineAPIClient: {e}")
                app_state["llm_client"] = None
        else:
            print("Online API credentials or model not fully configured.")
            app_state["llm_client"] = None
    else:  # 使用Ollama
        if ollama_url and ollama_model:
            try:
                app_state["llm_client"] = OllamaClient(
                    api_url=ollama_url,
                    default_model=ollama_model  # 使用Ollama配置中的模型名
                )
                print(f"Initialized OllamaClient with model: {ollama_model}")
            except Exception as e:
                print(f"Error initializing OllamaClient: {e}")
                app_state["llm_client"] = None
        else:
            print("Ollama API URL or model not configured.")
            app_state["llm_client"] = None

    # NovelProcessor 和 NarrativeEngine 将使用 app_state["llm_client"]
    # 这个客户端的 default_model 就是上面根据 use_online_api 选定的模型
    # 如果需要为分析和写作使用不同模型，NovelProcessor 和 NarrativeEngine 初始化时需要传入特定模型名
    # 或者 LLMClient 内部支持按需切换模型（当前接口设计是每个客户端一个 default_model）

    # 兼容旧的命名方式，主要给前端或其他地方可能直接引用的地方
    if app_state["llm_client"]:
        app_state["analysis_llm_client"] = app_state["llm_client"]
        app_state["writing_llm_client"] = app_state["llm_client"]
        # 更新前端显示的分析和写作模型名 (基于当前 llm_client 的 default_model)
        app_state["analysis_model_name"] = app_state["llm_client"].default_model
        app_state["writing_model_name"] = app_state["llm_client"].default_model

    else:
        print("LLM Client initialization failed.")
        app_state["analysis_llm_client"] = None
        app_state["writing_llm_client"] = None
        app_state["analysis_model_name"] = "N/A"
        app_state["writing_model_name"] = "N/A"


# 初始化应用状态 (在所有函数定义之后执行一次)
init_app_state()


@app.route('/')
def index():
    # 每次访问主页时，确保 app_state 与最新的持久化配置同步，尤其是模型列表等
    # 并重新加载历史对话，以防其他操作修改了它们
    # init_app_state() # 或者只更新部分关键状态
    current_config = config_manager.load_api_configs(DATA_DIR)
    app_state["available_ollama_models"] = current_config.get("available_ollama_models", [])
    app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)

    # 更新前端显示的分析和写作模型名，以反映当前实际客户端的默认模型
    if app_state.get("llm_client") and hasattr(app_state["llm_client"], 'default_model'):
        app_state["analysis_model_name"] = app_state["llm_client"].default_model
        app_state["writing_model_name"] = app_state["llm_client"].default_model
    else:  # 如果客户端未初始化成功
        app_state["analysis_model_name"] = current_config.get("selected_ollama_model") if not current_config.get(
            "use_online_api") else current_config.get("online_api_model", "N/A")
        app_state["writing_model_name"] = app_state["analysis_model_name"]  # 假设分析和写作模型一致

    return render_template('index.html', app_state=app_state)


@app.route('/api/update_api_config', methods=['POST'])
def update_api_config_route():  # 重命名以避免与模块名冲突
    data = request.json
    updates = {}

    # 基本配置
    if "use_online_api" in data:
        updates["use_online_api"] = data["use_online_api"]
        app_state["use_online_api"] = data["use_online_api"]

    # Ollama API配置
    if "ollama_api_url" in data:
        updates["ollama_api_url"] = data["ollama_api_url"]
        app_state["ollama_api_url_config"] = data["ollama_api_url"]
        app_state["ollama_api_url"] = data["ollama_api_url"]

    # 在线API配置
    if "online_api_url" in data:
        updates["online_api_url"] = data["online_api_url"]
        app_state["online_api_url"] = data["online_api_url"]

    if "online_api_key" in data:
        updates["online_api_key"] = data["online_api_key"]
        app_state["online_api_key"] = data["online_api_key"]

    # 模型选择 (这些字段名需要与前端js发送的一致)
    # 前端js发送的是 analysis_model_name 和 writing_model_name,
    # 以及更详细的自定义模型设置。
    # 这里需要根据 API 类型（Ollama/Online）和选择的模型类型（预设/自定义）来更新正确的配置项。

    selected_analysis_model_value = data.get("analysis_model_name")  # e.g. "llama3", "mistral", "custom"
    selected_writing_model_value = data.get("writing_model_name")  # e.g. "llama3", "mistral", "custom"

    # 根据前端选择更新实际使用的模型 (selected_ollama_model 或 online_api_model)
    # 假设分析和写作使用相同的 LLM Client 实例，但可能指向该实例内不同的模型（如果客户端支持）
    # 当前设计是每个 LLMClient 实例有一个 default_model。
    # 如果分析和写作模型不同，并且都用Ollama，则需要两个OllamaClient实例或一个支持模型切换的实例。
    # 简化处理：我们更新配置中用于初始化单一 LLMClient 的模型。
    # 如果用户选了Ollama，则更新 selected_ollama_model；如果选了Online，则更新 online_api_model。

    if not app_state.get("use_online_api"):  # 使用Ollama
        # 优先使用自定义Ollama模型（如果选择了自定义且类型为Ollama）
        if selected_analysis_model_value == "custom" and data.get("analysis_custom_type") == "ollama":
            updates["selected_ollama_model"] = data.get("analysis_custom_ollama_model")
        elif selected_analysis_model_value != "custom" and selected_analysis_model_value:  # 预设的Ollama模型
            updates["selected_ollama_model"] = selected_analysis_model_value  # 假设预设名就是Ollama模型名
        # 如果只更新了 writing_model 且是Ollama自定义
        elif selected_writing_model_value == "custom" and data.get("writing_custom_type") == "ollama":
            updates["selected_ollama_model"] = data.get("writing_custom_ollama_model")
        elif selected_writing_model_value != "custom" and selected_writing_model_value:
            updates["selected_ollama_model"] = selected_writing_model_value

        # 更新 app_state 以便 init_llm_client 使用
        if "selected_ollama_model" in updates:
            app_state["selected_ollama_model"] = updates["selected_ollama_model"]

    else:  # 使用在线API
        if selected_analysis_model_value == "custom" and data.get("analysis_custom_type") == "online":
            updates["online_api_model"] = data.get("analysis_custom_online_model")
        elif selected_analysis_model_value != "custom" and selected_analysis_model_value:
            updates["online_api_model"] = selected_analysis_model_value  # 假设预设名也是在线模型名 (可能需要映射)

        elif selected_writing_model_value == "custom" and data.get("writing_custom_type") == "online":
            updates["online_api_model"] = data.get("writing_custom_online_model")
        elif selected_writing_model_value != "custom" and selected_writing_model_value:
            updates["online_api_model"] = selected_writing_model_value

        if "online_api_model" in updates:
            app_state["online_api_model"] = updates["online_api_model"]

    # 更新前端表单中 analysis_model_name 和 writing_model_name 的状态
    if "analysis_model_name" in data:
        app_state["analysis_model_name"] = data["analysis_model_name"]  # 这是UI选择的名称
        updates["analysis_model_name"] = data["analysis_model_name"]  # 保存UI选择，方便下次加载
    if "analysis_custom_type" in data:
        app_state["analysis_custom_type"] = data["analysis_custom_type"]
        updates["analysis_custom_type"] = data["analysis_custom_type"]
    if "analysis_custom_ollama_model" in data:
        app_state["analysis_custom_ollama_model"] = data["analysis_custom_ollama_model"]
        updates["analysis_custom_ollama_model"] = data["analysis_custom_ollama_model"]
    if "analysis_custom_online_model" in data:
        app_state["analysis_custom_online_model"] = data["analysis_custom_online_model"]
        updates["analysis_custom_online_model"] = data["analysis_custom_online_model"]

    if "writing_model_name" in data:
        app_state["writing_model_name"] = data["writing_model_name"]
        updates["writing_model_name"] = data["writing_model_name"]
    if "writing_custom_type" in data:
        app_state["writing_custom_type"] = data["writing_custom_type"]
        updates["writing_custom_type"] = data["writing_custom_type"]
    if "writing_custom_ollama_model" in data:
        app_state["writing_custom_ollama_model"] = data["writing_custom_ollama_model"]
        updates["writing_custom_ollama_model"] = data["writing_custom_ollama_model"]
    if "writing_custom_online_model" in data:
        app_state["writing_custom_online_model"] = data["writing_custom_online_model"]
        updates["writing_custom_online_model"] = data["writing_custom_online_model"]

    # 模型参数 (这些直接更新到 app_state 和 updates)
    model_param_keys = ["temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty"]
    for key in model_param_keys:
        if key in data:
            updates[key] = data[key]
            app_state[key] = data[key]

    # 叙事窗口设置
    narrative_setting_keys = ["initial_context_chapters", "window_before", "window_after", "divergence_threshold"]
    for key in narrative_setting_keys:
        if key in data:
            updates[key] = data[key]
            app_state[key] = data[key]
            if key == "window_before": app_state["narrative_window_chapter_before"] = data[key]
            if key == "window_after": app_state["narrative_window_chapter_after"] = data[key]

    # 更新配置文件
    config_manager.update_api_config(DATA_DIR, updates)

    # 重新初始化LLM客户端以应用新的API或模型设置
    init_llm_client()

    return jsonify({'success': True, 'message': 'API配置已更新'})


@app.route('/api/refresh_ollama_models', methods=['POST'])
def refresh_ollama_models():
    data = request.json
    api_url = data.get('api_url', app_state.get("ollama_api_url"))  # 优先使用传入的，否则用app_state的

    if not api_url:
        return jsonify({'success': False, 'error': 'Ollama API URL不能为空'})

    try:
        # 创建临时Ollama客户端实例来获取模型列表
        temp_client = OllamaClient(api_url=api_url, default_model="any")  # default_model 在这里不重要

        models_data = temp_client.list_local_models()  # 这个方法返回 [{"name": "model_name"}, ...]

        if models_data is not None:  # list_local_models 可能返回 None 或 []
            model_names = [m.get("name") for m in models_data if m.get("name")]
            app_state["available_ollama_models"] = model_names
            config_manager.update_api_config(DATA_DIR, {"available_ollama_models": model_names})
            return jsonify({'success': True, 'models': model_names})
        else:
            return jsonify({'success': False, 'error': '获取Ollama模型列表失败或列表为空'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'获取Ollama模型列表时出错: {str(e)}'})


@app.route('/api/test_api', methods=['POST'])
def test_api():
    data = request.json
    test_message = data.get('message', '')

    if not test_message:
        return jsonify({'success': False, 'error': '测试消息不能为空'})

    # 确保LLM客户端已根据当前配置初始化
    if not app_state.get("llm_client"):
        init_llm_client()  # 尝试重新初始化
        if not app_state.get("llm_client"):
            return jsonify({'success': False, 'error': 'LLM客户端未能初始化，请检查API配置'})

    current_llm_client = app_state["llm_client"]

    try:
        # 使用 LLMClientInterface 的 generate_chat_completion 方法
        response_data = current_llm_client.generate_chat_completion(
            model=current_llm_client.default_model,  # 使用客户端的默认模型进行测试
            messages=[
                {"role": "system", "content": "你是一个有用的AI助手。"},
                {"role": "user", "content": test_message}
            ]
        )

        if response_data and response_data.get("message") and response_data.get("message").get("content"):
            return jsonify({'success': True, 'response': response_data["message"]["content"]})
        else:
            error_detail = f"API响应格式不符合预期: {response_data}" if response_data else "API未返回有效响应"
            return jsonify({'success': False, 'error': f'获取API响应失败。{error_detail}'})
    except Exception as e:
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
    novel_title = novel_title_from_form if novel_title_from_form else os.path.splitext(file.filename)[0]
    secure_name = secure_filename(novel_title if novel_title_from_form else file.filename)  # 使用小说标题或原文件名来生成安全目录名

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:8]

    # 使用安全处理过的小说名和时间戳创建唯一的目录，而不是原始文件名
    # 这样即使用户上传同名文件（但标题不同）也能区分
    # 并且避免了原始文件名可能带来的路径问题
    novel_base_name_for_dir = utils.sanitize_filename(novel_title if novel_title else "untitled_novel")
    per_novel_upload_dir_name = f"{timestamp}_{novel_base_name_for_dir}_{unique_id}"

    # upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], per_novel_upload_dir_name) # 原TXT文件保存的目录
    # os.makedirs(upload_dir, exist_ok=True)
    # file_path = os.path.join(upload_dir, secure_filename(file.filename)) # 保存原始上传文件
    # file.save(file_path)

    # 小说数据目录 (用于章节、分析等)
    novel_data_dir = os.path.join(DATA_DIR, per_novel_upload_dir_name)
    os.makedirs(novel_data_dir, exist_ok=True)

    # 将上传的TXT文件直接保存到其专属的 novel_data_dir 中，而不是 uploads 文件夹
    # 这样每个小说的所有相关文件（原始txt, chapters, analysis）都在一个目录下
    file_path_in_data_dir = os.path.join(novel_data_dir, secure_filename(file.filename))
    file.seek(0)  # 重置文件指针以防万一
    file.save(file_path_in_data_dir)

    app_state["app_stage"] = "processing"
    app_state["novel_title"] = novel_title
    app_state["novel_data_dir"] = novel_data_dir
    app_state["chapters_dir"] = os.path.join(novel_data_dir, 'chapters')  # NovelProcessor 会创建这个
    app_state["analysis_path"] = os.path.join(novel_data_dir, 'final_analysis.json')

    app_state["novel_specific_data_dir_ui"] = novel_data_dir
    app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
    app_state["final_analysis_path_ui"] = app_state["analysis_path"]

    if not app_state.get("llm_client"):  # 确保客户端已初始化
        init_llm_client()
        if not app_state.get("llm_client"):
            app_state["app_stage"] = "config_novel"  # 回到配置阶段
            return jsonify({'success': False, 'error': 'LLM客户端初始化失败，请检查API配置后再上传。'})

    novel_processor = NovelProcessor(
        llm_client=app_state["llm_client"],  # 传递的是 OllamaClient 或 GenericOnlineAPIClient 实例
        novel_file_path=file_path_in_data_dir,  # 使用保存在 novel_data_dir 中的路径
        output_dir=novel_data_dir  # 输出也到这个目录
    )

    success = novel_processor.process_novel()

    if success:
        final_analysis = utils.read_json_file(app_state["analysis_path"])
        if final_analysis:
            app_state["app_stage"] = "initializing_narrative"
            app_state["novel_title"] = final_analysis.get("title", novel_title)  # 优先用分析结果的标题

            if "excerpts" in final_analysis and final_analysis["excerpts"]:
                app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "暂无精选片段")
            else:
                app_state["novel_excerpt"] = "分析完成，但未找到精选片段。"

            if "world_building" in final_analysis and final_analysis["world_building"]:
                # 将世界观条目合并显示
                wb_texts = [f"{item.get('name', '')}: {item.get('description', '')}" for item in
                            final_analysis["world_building"]]
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
        return jsonify({'success': False, 'error': '处理小说失败，请检查后台日志。'})


@app.route('/start_narrative', methods=['POST'])
def start_narrative():
    if app_state.get("app_stage") != "initializing_narrative":
        return jsonify(
            {'success': False, 'error': '应用状态不正确，无法开始叙事。当前状态: ' + app_state.get("app_stage", "未知")})

    if not app_state.get("llm_client"):
        init_llm_client()
        if not app_state.get("llm_client"):
            return jsonify({'success': False, 'error': 'LLM客户端初始化失败，无法开始叙事。'})

    # 从持久化配置中获取模型参数，而不是 app_state，以确保使用的是最新保存的设置
    current_api_config = config_manager.load_api_configs(DATA_DIR)
    model_params = config_manager.get_model_params(current_api_config)

    # 确定写作模型，NarrativeEngine 需要一个模型名参数
    # 当前设计中，app_state["llm_client"] 已经根据选择（Ollama或Online）及其对应模型初始化
    # 所以 NarrativeEngine 使用这个客户端的 default_model 即可
    writing_model_for_engine = app_state["llm_client"].default_model

    app_state["narrative_engine"] = NarrativeEngine(
        llm_client=app_state["llm_client"],  # 传递客户端实例
        novel_data_dir=app_state["novel_data_dir"],
        chapters_dir=app_state["chapters_dir"],  # NovelProcessor 已创建
        analysis_path=app_state["analysis_path"],
        model_name=writing_model_for_engine,  # 传递实际使用的模型名给引擎记录
        saved_state=app_state.get("engine_state_to_load")  # 如果是从存档加载
    )
    app_state["engine_state_to_load"] = None  # 清除已加载的存档状态

    initial_narrative = app_state["narrative_engine"].initialize_narrative_session(
        initial_context_chapters=current_api_config.get("initial_context_chapters", 3),
        window_before=current_api_config.get("window_before", 2),
        window_after=current_api_config.get("window_after", 2),
        divergence_threshold=current_api_config.get("divergence_threshold", 0.7),
        model_params=model_params
    )

    if initial_narrative is not None:  # initialize_narrative_session 可能返回 None
        app_state["app_stage"] = "narrating"
        # narrative_engine 内部会管理自己的 conversation_history
        # 更新 narrative_history_display 以便前端正确显示
        app_state["narrative_history_display"] = []
        if hasattr(app_state["narrative_engine"], 'conversation_history'):
            for entry in app_state["narrative_engine"].conversation_history:
                speaker = "用户" if entry.get("role") == "user" else ("系统" if entry.get("role") == "system" else "AI")
                app_state["narrative_history_display"].append((speaker, entry.get("content", "")))

        return jsonify({'success': True, 'initial_narrative': initial_narrative})
    else:
        # 如果初始化失败，尝试获取引擎的错误信息（如果引擎内部有记录）
        error_msg = "初始化叙事会话失败。"
        if hasattr(app_state["narrative_engine"], 'last_error') and app_state["narrative_engine"].last_error:
            error_msg += f" 详情: {app_state['narrative_engine'].last_error}"
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

    if response is not None:  # process_user_action 可能返回 None
        app_state["narrative_history_display"] = []  # 重建显示历史
        if hasattr(app_state["narrative_engine"], 'conversation_history'):
            for entry in app_state["narrative_engine"].conversation_history:
                speaker = "用户" if entry.get("role") == "user" else ("系统" if entry.get("role") == "system" else "AI")
                app_state["narrative_history_display"].append((speaker, entry.get("content", "")))
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

    # save_manager.save_game_state 现在应该直接调用 narrative_engine 的保存方法
    # narrative_engine.save_state_to_file() 会返回路径
    save_path = app_state["narrative_engine"].save_state_to_file()  # Engine 知道自己的 novel_data_dir

    if save_path:
        return jsonify({'success': True, 'save_path': save_path, 'message': '游戏已保存！'})
    else:
        return jsonify({'success': False, 'error': '保存游戏状态失败'})


@app.route('/load_game', methods=['POST'])
def load_game():  # 注意：这个路由似乎在前端JS中未被直接使用，前端用的是 /api/history/load
    data = request.json
    save_path = data.get('save_path', '')

    if not save_path or not os.path.exists(save_path):
        return jsonify({'success': False, 'error': '存档路径无效'})

    save_data = save_manager.load_game_state(save_path)  # load_game_state 读取JSON文件

    if save_data:
        app_state["engine_state_to_load"] = save_data  # 这个是完整的存档内容，NarrativeEngine的构造函数会处理它

        # 从存档数据中恢复关键路径信息到 app_state
        # NarrativeEngine 的 saved_state 参数期望的是 get_state_for_saving() 的输出格式
        # 其中包含了 novel_data_dir, chapters_dir, analysis_path, model_name
        engine_saved_state = save_data.get("engine_state") if "engine_state" in save_data else save_data  # 兼容旧格式

        app_state["novel_data_dir"] = engine_saved_state.get("novel_data_dir", "")
        app_state["chapters_dir"] = engine_saved_state.get("chapters_dir", "")
        app_state["analysis_path"] = engine_saved_state.get("analysis_path", "")

        app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
        app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
        app_state["final_analysis_path_ui"] = app_state["analysis_path"]

        # 尝试加载并显示小说基本信息
        if os.path.exists(app_state["analysis_path"]):
            final_analysis = utils.read_json_file(app_state["analysis_path"])
            if final_analysis:
                app_state["novel_title"] = final_analysis.get("title", "未知小说")
                if "excerpts" in final_analysis and final_analysis["excerpts"]:
                    app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "")
                if "world_building" in final_analysis and final_analysis["world_building"]:
                    wb_texts = [f"{item.get('name', '')}: {item.get('description', '')}" for item in
                                final_analysis["world_building"]]
                    app_state["world_setting"] = "\n".join(wb_texts) if wb_texts else ""
                if "characters" in final_analysis and final_analysis["characters"]:
                    app_state["character_info"] = final_analysis["characters"][0]

        app_state["app_stage"] = "initializing_narrative"  # 准备好初始化叙事
        return jsonify({'success': True, 'message': '存档已加载，准备开始旅程。'})
    else:
        return jsonify({'success': False, 'error': '加载游戏状态失败'})


@app.route('/api/saves/list', methods=['GET'])
def get_saves_list_route():  # 重命名
    # 存档列表是基于当前激活的小说的 (app_state["novel_data_dir"])
    if not app_state.get("novel_data_dir") or not os.path.exists(app_state["novel_data_dir"]):
        return jsonify({'success': True, 'saves': [], 'message': '当前无激活小说，无法列出存档。'})

    saves = save_manager.get_saves_list(app_state["novel_data_dir"])
    return jsonify({'success': True, 'saves': saves})


@app.route('/api/history/list', methods=['GET'])
def get_history_list_route():  # 重命名
    history_list = history_manager.load_history_conversations(DATA_DIR)  # 历史是全局的
    app_state["history_conversations"] = history_list  # 更新app_state
    return jsonify({'success': True, 'history': history_list})


@app.route('/api/history/save', methods=['POST'])
def save_history_route():  # 重命名
    if app_state.get("app_stage") != "narrating" or not app_state.get("narrative_engine"):
        return jsonify({'success': False, 'error': '当前无正在进行的叙事，无法保存到历史。'})

    current_api_config = config_manager.load_api_configs(DATA_DIR)
    # app_config_for_history 应该包含与此会话相关的配置
    app_config_for_history = {
        "temperature": current_api_config.get("temperature"),
        "top_p": current_api_config.get("top_p"),
        "max_tokens": current_api_config.get("max_tokens"),
        "frequency_penalty": current_api_config.get("frequency_penalty"),
        "presence_penalty": current_api_config.get("presence_penalty"),
        "initial_context_chapters": current_api_config.get("initial_context_chapters"),
        "window_before": current_api_config.get("window_before"),
        "window_after": current_api_config.get("window_after"),
        "divergence_threshold": current_api_config.get("divergence_threshold"),
        "use_online_api": current_api_config.get("use_online_api"),
        "selected_ollama_model": current_api_config.get("selected_ollama_model"),  # 保存当时模型
        "online_api_model": current_api_config.get("online_api_model"),  # 保存当时模型
        # 注意：API Key 不应保存到历史记录中
        # "analysis_model_name" and "writing_model_name" (UI selectors)
        "analysis_model_name_ui": app_state.get("analysis_model_name"),
        "writing_model_name_ui": app_state.get("writing_model_name"),

    }

    history_path = history_manager.save_current_conversation(
        data_dir=DATA_DIR,  # 历史记录保存在全局 data/history
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
def delete_history_route():  # 重命名
    data = request.json
    file_path = data.get('file_path', '')

    if not file_path:  # 简单验证
        return jsonify({'success': False, 'error': '未提供文件路径'})

    # 安全性：确保 file_path 在预期的 HISTORY_DIR 内 (这里简化，假设路径来自可信源即前端列表)
    # full_path = os.path.join(DATA_DIR, history_manager.HISTORY_DIR, os.path.basename(file_path))
    # if not os.path.exists(full_path):
    #    return jsonify({'success': False, 'error': '历史对话文件路径无效'})

    # 前端传来的 file_path 应该是绝对或相对于项目根目录的，或者已经是 data/history 下的完整路径
    # history_manager.delete_history_conversation 应该能处理它

    success = history_manager.delete_history_conversation(file_path)  # 直接使用前端提供的路径

    if success:
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)  # 刷新
        return jsonify({'success': True, 'message': '历史对话已删除。'})
    else:
        return jsonify({'success': False, 'error': '删除历史对话失败'})


@app.route('/api/history/load', methods=['POST'])
def load_history_route():  # 重命名
    data = request.json
    file_path = data.get('file_path', '')

    if not file_path or not os.path.exists(file_path):  # 检查文件是否存在
        return jsonify({'success': False, 'error': '历史对话文件路径无效或文件不存在。'})

    try:
        history_item_data = utils.read_json_file(file_path)  # history_item_data 是完整的存档内容
        if not history_item_data:
            return jsonify({'success': False, 'error': '加载历史对话数据失败或文件为空。'})

        # load_conversation_from_history 只是从 history_item_data 中提取 app_config 和 engine_state
        result = history_manager.load_conversation_from_history(history_item_data)

        if result.get("success"):
            loaded_app_config = result.get("app_config", {})
            engine_state_to_load = result.get("engine_state")

            # 更新当前应用的配置以匹配历史会话的配置
            config_updates = {}
            for key, value in loaded_app_config.items():
                if key in app_state:  # 只更新 app_state 中存在的键
                    app_state[key] = value
                # 也准备更新到 api_config.json
                # 但要注意，不是所有 loaded_app_config 的键都直接对应 api_config.json 的顶级键
                if key in config_manager.load_api_configs(DATA_DIR):  # 检查是否是 config_manager 管理的键
                    config_updates[key] = value

            if config_updates:
                config_manager.update_api_config(DATA_DIR, config_updates)

            # 重新初始化LLM客户端以应用加载的配置
            init_llm_client()
            if not app_state.get("llm_client"):
                return jsonify({'success': False, 'error': '根据历史记录配置LLM客户端失败。'})

            app_state["engine_state_to_load"] = engine_state_to_load  # 这是 NarrativeEngine 初始化时需要的状态

            # 从 engine_state_to_load 中恢复小说相关路径
            if engine_state_to_load:
                app_state["novel_data_dir"] = engine_state_to_load.get("novel_data_dir", "")
                app_state["chapters_dir"] = engine_state_to_load.get("chapters_dir", "")
                app_state["analysis_path"] = engine_state_to_load.get("analysis_path", "")

                app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
                app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
                app_state["final_analysis_path_ui"] = app_state["analysis_path"]

                # 尝试加载并显示小说基本信息
                if os.path.exists(app_state["analysis_path"]):
                    final_analysis = utils.read_json_file(app_state["analysis_path"])
                    if final_analysis:
                        app_state["novel_title"] = final_analysis.get("title", "未知小说")
                        if "excerpts" in final_analysis and final_analysis["excerpts"]:
                            app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "")
                        if "world_building" in final_analysis and final_analysis["world_building"]:
                            wb_texts = [f"{item.get('name', '')}: {item.get('description', '')}" for item in
                                        final_analysis["world_building"]]
                            app_state["world_setting"] = "\n".join(wb_texts) if wb_texts else ""
                        if "characters" in final_analysis and final_analysis["characters"]:
                            app_state["character_info"] = final_analysis["characters"][0]
                else:  # 如果分析文件路径无效，尝试从历史元数据获取小说名
                    if "metadata" in history_item_data and "novel_name" in history_item_data["metadata"]:
                        app_state["novel_title"] = history_item_data["metadata"]["novel_name"]

            app_state["app_stage"] = "initializing_narrative"  # 设置好状态，等待用户点击 "开始旅程"
            return jsonify({'success': True, 'message': '历史对话已加载，小说信息已更新，准备开始旅程。'})
        else:
            return jsonify({'success': False, 'error': result.get("error", "从历史记录提取对话数据失败。")})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'加载历史对话时发生意外错误: {str(e)}'})


@app.route('/api/config/reset', methods=['POST'])
def reset_config_route():  # 重命名
    default_config = config_manager.reset_api_config(DATA_DIR)  # 重置并保存到文件

    # 更新当前 app_state 以反映重置后的配置
    for key, value in default_config.items():
        if key in app_state:
            app_state[key] = value

    init_llm_client()  # 基于重置后的配置重新初始化客户端
    return jsonify({'success': True, 'message': 'API及应用配置已重置为默认值。'})


@app.route('/update_settings', methods=['POST'])
def update_settings_route():  # 重命名
    data = request.json
    updates_for_config_file = {}  # 只包含需要保存到 api_config.json 的项

    # UI相关的设置直接更新 app_state
    if "show_typing_animation" in data:
        app_state["show_typing_animation"] = data["show_typing_animation"]
    if "typing_speed" in data:
        app_state["typing_speed"] = data["typing_speed"]
    if "enable_keyboard_shortcuts" in data:
        app_state["enable_keyboard_shortcuts"] = data["enable_keyboard_shortcuts"]

    # 模型参数和叙事窗口设置需要更新 app_state 并保存到 config_manager
    model_param_keys = ["temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty"]
    for key in model_param_keys:
        if key in data:
            app_state[key] = data[key]
            updates_for_config_file[key] = data[key]

    narrative_setting_keys = ["initial_context_chapters", "window_before", "window_after", "divergence_threshold"]
    for key in narrative_setting_keys:
        if key in data:
            app_state[key] = data[key]
            updates_for_config_file[key] = data[key]
            if key == "window_before": app_state["narrative_window_chapter_before"] = data[key]
            if key == "window_after": app_state["narrative_window_chapter_after"] = data[key]

    if updates_for_config_file:
        config_manager.update_api_config(DATA_DIR, updates_for_config_file)
        # 如果更新了影响LLM客户端的参数，可能需要重新初始化
        # init_llm_client() # 如果 temperature, top_p 等会影响客户端实例化或默认行为

    return jsonify({'success': True, 'message': '设置已更新。'})


@app.route('/reset_journey', methods=['POST'])
def reset_journey_route():  # 重命名
    reset_for_new_journey()  # 这个函数内部会处理 app_state 和 LLM 客户端
    return jsonify({'success': True, 'message': '应用已重置，可以开始新的旅程。'})


if __name__ == '__main__':
    # 确保在启动时执行一次 init_app_state，以加载配置并初始化客户端
    # init_app_state() 已经在全局作用域被调用了
    app.run(debug=True, host='0.0.0.0', port=5000)