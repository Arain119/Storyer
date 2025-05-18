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
                                                        "gemma3:12b-it-q8_0")
    app_state["online_api_url"] = api_config.get("online_api_url", "")
    app_state["online_api_model"] = api_config.get("online_api_model", "")
    app_state["online_api_key"] = api_config.get("online_api_key", "")

    # 前端UI选择的模型类型 (e.g., "llama3", "custom")
    app_state["analysis_model_name"] = api_config.get("analysis_model_name", "llama3")
    app_state["analysis_custom_type"] = api_config.get("analysis_custom_type", "ollama")
    app_state["analysis_custom_ollama_model"] = api_config.get("analysis_custom_ollama_model", "")
    app_state["analysis_custom_online_model"] = api_config.get("analysis_custom_online_model", "")

    app_state["writing_model_name"] = api_config.get("writing_model_name", "llama3")
    app_state["writing_custom_type"] = api_config.get("writing_custom_type", "ollama")
    app_state["writing_custom_ollama_model"] = api_config.get("writing_custom_ollama_model", "")
    app_state["writing_custom_online_model"] = api_config.get("writing_custom_online_model", "")

    app_state["available_ollama_models"] = api_config.get("available_ollama_models",
                                                          ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0"])
    app_state["app_stage"] = "config_novel"

    app_state["novel_title"] = ""
    app_state["novel_excerpt"] = ""
    app_state["world_setting"] = ""
    app_state["character_info"] = None

    app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
    app_state["show_history_panel"] = True  # 此状态似乎未在前端JS中动态使用

    app_state["narrative_history_display"] = []

    app_state["narrative_engine"] = None
    app_state["engine_state_to_load"] = None

    app_state["novel_data_dir"] = ""
    app_state["chapters_dir"] = ""
    app_state["analysis_path"] = ""
    # UI显示路径，与实际路径一致
    app_state["novel_specific_data_dir_ui"] = ""
    app_state["chapters_data_path_ui"] = ""
    app_state["final_analysis_path_ui"] = ""

    app_state["initial_context_chapters"] = api_config.get("initial_context_chapters", 3)
    # window_before/after 用于叙事引擎内部获取上下文，narrative_window_chapter_before/after 是UI上的显示/配置项
    app_state["window_before"] = api_config.get("window_before", 2)
    app_state["window_after"] = api_config.get("window_after", 2)
    app_state["narrative_window_chapter_before"] = api_config.get("window_before", 2)  # 保持同步
    app_state["narrative_window_chapter_after"] = api_config.get("window_after", 2)  # 保持同步
    app_state["divergence_threshold"] = api_config.get("divergence_threshold", 0.7)

    app_state["temperature"] = api_config.get("temperature", 0.7)
    app_state["top_p"] = api_config.get("top_p", 0.9)
    app_state["max_tokens"] = api_config.get("max_tokens", 1024)
    app_state["frequency_penalty"] = api_config.get("frequency_penalty", 0.0)
    app_state["presence_penalty"] = api_config.get("presence_penalty", 0.0)

    app_state["show_typing_animation"] = api_config.get("show_typing_animation", True)
    app_state["typing_speed"] = api_config.get("typing_speed", 50)
    app_state["enable_keyboard_shortcuts"] = api_config.get("enable_keyboard_shortcuts", True)

    app_state["llm_client"] = None
    # analysis_llm_client 和 writing_llm_client 仅作为 app_state["llm_client"] 的别名或旧版兼容
    app_state["analysis_llm_client"] = None
    app_state["writing_llm_client"] = None

    init_llm_client()


def reset_for_new_journey():
    """重置应用状态以准备新的旅程，但保留API和部分UI配置。"""
    # 重新加载持久化的配置
    init_app_state()  # 这会从 api_config.json 重新加载所有配置

    # 清理特定于当前小说的状态
    app_state["app_stage"] = "config_novel"
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

    # 确保LLM客户端基于最新的（可能被保留的）配置重新初始化
    # init_app_state() 内部已经调用了 init_llm_client()


def init_llm_client():
    """根据当前配置初始化LLM客户端。"""
    app_state["llm_client"] = None  # 清理旧实例
    current_config = config_manager.load_api_configs(DATA_DIR)

    use_online = current_config.get("use_online_api", False)

    # 确定实际使用的模型名和API类型
    # analysis_model_name 和 writing_model_name 在UI上是分开选的，但这里我们假设它们最终指向同一个LLM客户端实例
    # 如果需要真正独立的分析/写作客户端，则需要更复杂的逻辑

    # 以 "writing_model" (叙事模型) 的配置为准来初始化主 llm_client
    # 因为分析阶段的 NovelProcessor 也会接收这个 llm_client 实例
    # 如果分析和写作模型不同，NovelProcessor 和 NarrativeEngine 初始化时可以被告知使用哪个具体模型名（如果客户端支持切换）
    # 目前的 LLMClientInterface 实现是每个客户端有一个 default_model

    client_to_init = None
    model_for_client = None

    if use_online:
        api_url = current_config.get("online_api_url")
        api_key = current_config.get("online_api_key")
        # 根据 writing_model_name 的选择来确定在线模型的具体名称
        if current_config.get("writing_model_name") == "custom" and current_config.get(
                "writing_custom_type") == "online":
            model_for_client = current_config.get("writing_custom_online_model")
        else:  # 预设模型或非自定义在线模型
            model_for_client = current_config.get("online_api_model")  # 使用在线API部分指定的通用模型名

        if api_url and api_key and model_for_client:
            try:
                client_to_init = GenericOnlineAPIClient(api_url=api_url, api_key=api_key,
                                                        default_model=model_for_client)
                print(f"Initialized GenericOnlineAPIClient with model: {model_for_client}")
            except Exception as e:
                print(f"Error initializing GenericOnlineAPIClient: {e}")
        else:
            print("Online API credentials or model not fully configured for writing.")
    else:  # 使用Ollama
        api_url = current_config.get("ollama_api_url")
        if current_config.get("writing_model_name") == "custom" and current_config.get(
                "writing_custom_type") == "ollama":
            model_for_client = current_config.get("writing_custom_ollama_model")
        else:  # 预设模型或非自定义Ollama模型
            model_for_client = current_config.get("selected_ollama_model")  # 使用Ollama部分指定的通用模型名

        if api_url and model_for_client:
            try:
                client_to_init = OllamaClient(api_url=api_url, default_model=model_for_client)
                print(f"Initialized OllamaClient with model: {model_for_client}")
            except Exception as e:
                print(f"Error initializing OllamaClient: {e}")
        else:
            print("Ollama API URL or model not configured for writing.")

    app_state["llm_client"] = client_to_init
    app_state["analysis_llm_client"] = client_to_init  # 别名
    app_state["writing_llm_client"] = client_to_init  # 别名

    # 更新UI显示的分析和写作模型名称，以反映当前客户端的实际默认模型
    if client_to_init:
        # app_state["analysis_model_name"] = client_to_init.default_model # 这个是UI选择的，不应该被覆盖
        # app_state["writing_model_name"] = client_to_init.default_model # 这个是UI选择的，不应该被覆盖
        pass  # UI上的 analysis_model_name 和 writing_model_name 应该由用户选择驱动并保存到配置
        # init_app_state() 会从配置加载它们
    else:
        print("LLM Client initialization failed.")
        # app_state["analysis_model_name"] = "N/A" # 保留用户在UI的选择或配置中的值
        # app_state["writing_model_name"] = "N/A"


init_app_state()


@app.route('/')
def index():
    # 每次访问主页时，确保 app_state 与最新的持久化配置同步
    # init_app_state() 在启动时已调用，这里可以只更新需要频繁刷新的部分
    current_config = config_manager.load_api_configs(DATA_DIR)
    app_state["available_ollama_models"] = current_config.get("available_ollama_models", [])
    app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)

    # 确保UI显示的API URL与配置一致
    app_state["ollama_api_url_config"] = current_config.get("ollama_api_url", "http://127.0.0.1:11434")
    app_state["online_api_url"] = current_config.get("online_api_url", "")
    app_state["online_api_key"] = current_config.get("online_api_key", "")  # 确保密码字段不直接传到模板，除非必要

    # 确保UI选择的模型名与配置一致
    app_state["analysis_model_name"] = current_config.get("analysis_model_name", "llama3")
    app_state["analysis_custom_type"] = current_config.get("analysis_custom_type", "ollama")
    app_state["analysis_custom_ollama_model"] = current_config.get("analysis_custom_ollama_model", "")
    app_state["analysis_custom_online_model"] = current_config.get("analysis_custom_online_model", "")
    app_state["writing_model_name"] = current_config.get("writing_model_name", "llama3")
    app_state["writing_custom_type"] = current_config.get("writing_custom_type", "ollama")
    app_state["writing_custom_ollama_model"] = current_config.get("writing_custom_ollama_model", "")
    app_state["writing_custom_online_model"] = current_config.get("writing_custom_online_model", "")

    # 更新前端主页卡片上显示的模型名称 (基于当前LLM客户端的实际模型)
    if app_state.get("llm_client") and hasattr(app_state["llm_client"], 'default_model'):
        # 这部分逻辑可能需要调整，因为分析和写作模型可以独立选择
        # 这里我们假设主页卡片显示的是写作模型（叙事引擎使用的模型）
        app_state["display_writing_model_on_card"] = app_state["llm_client"].default_model

        # 对于分析模型，需要根据分析模型的选择逻辑来确定显示哪个
        if current_config.get("analysis_model_name") == "custom":
            if current_config.get("analysis_custom_type") == "ollama":
                app_state["display_analysis_model_on_card"] = current_config.get("analysis_custom_ollama_model",
                                                                                 "Custom Ollama")
            else:
                app_state["display_analysis_model_on_card"] = current_config.get("analysis_custom_online_model",
                                                                                 "Custom Online")
        else:  # 预设模型
            # 如果是Ollama预设，需要找到对应的Ollama模型名 (假设预设名就是Ollama模型名或需要映射)
            # 如果是在线预设，也需要找到对应的在线模型名
            # 简化：直接使用 analysis_model_name (UI选择的那个)
            app_state["display_analysis_model_on_card"] = current_config.get("analysis_model_name", "N/A")
            if not current_config.get("use_online_api") and current_config.get("analysis_model_name") != "custom":
                app_state["display_analysis_model_on_card"] = current_config.get(
                    "selected_ollama_model")  # 如果用Ollama且非自定义，显示Ollama通用模型
            elif current_config.get("use_online_api") and current_config.get("analysis_model_name") != "custom":
                app_state["display_analysis_model_on_card"] = current_config.get(
                    "online_api_model")  # 如果用Online且非自定义，显示Online通用模型


    else:  # LLM客户端未初始化
        app_state["display_analysis_model_on_card"] = "N/A"
        app_state["display_writing_model_on_card"] = "N/A"

    return render_template('index.html', app_state=app_state)


@app.route('/api/update_api_config', methods=['POST'])
def update_api_config_route():
    data = request.json
    updates = {}  # 用于保存到 config_manager 的更新

    # 基本API类型选择
    if "use_online_api" in data:
        updates["use_online_api"] = data["use_online_api"]
        app_state["use_online_api"] = data["use_online_api"]

    # Ollama 配置
    if "ollama_api_url" in data:
        updates["ollama_api_url"] = data["ollama_api_url"]
        app_state["ollama_api_url_config"] = data["ollama_api_url"]  # UI显示用
        app_state["ollama_api_url"] = data["ollama_api_url"]  # 实际使用

    # 在线API 配置
    if "online_api_url" in data:
        updates["online_api_url"] = data["online_api_url"]
        app_state["online_api_url"] = data["online_api_url"]
    if "online_api_key" in data:
        updates["online_api_key"] = data["online_api_key"]
        app_state["online_api_key"] = data["online_api_key"]

    # 更新 selected_ollama_model (Ollama的通用模型) 和 online_api_model (在线API的通用模型)
    # 这些是 init_llm_client 在非自定义情况下会参考的模型
    if "selected_ollama_model" in data:  # 通常由 refresh_ollama_models 后用户选择或默认设置
        updates["selected_ollama_model"] = data["selected_ollama_model"]
        app_state["selected_ollama_model"] = data["selected_ollama_model"]
    if "online_api_model" in data:  # 用户在在线API部分输入的模型名
        updates["online_api_model"] = data["online_api_model"]
        app_state["online_api_model"] = data["online_api_model"]

    # 分析模型选择 (保存UI的选择状态)
    if "analysis_model_name" in data:  # "llama3", "mistral", "custom"
        updates["analysis_model_name"] = data["analysis_model_name"]
        app_state["analysis_model_name"] = data["analysis_model_name"]
    if "analysis_custom_type" in data:  # "ollama" or "online"
        updates["analysis_custom_type"] = data["analysis_custom_type"]
        app_state["analysis_custom_type"] = data["analysis_custom_type"]
    if "analysis_custom_ollama_model" in data:  # 具体自定义Ollama模型名
        updates["analysis_custom_ollama_model"] = data["analysis_custom_ollama_model"]
        app_state["analysis_custom_ollama_model"] = data["analysis_custom_ollama_model"]
    if "analysis_custom_online_model" in data:  # 具体自定义在线模型名
        updates["analysis_custom_online_model"] = data["analysis_custom_online_model"]
        app_state["analysis_custom_online_model"] = data["analysis_custom_online_model"]

    # 写作模型选择 (保存UI的选择状态)
    if "writing_model_name" in data:
        updates["writing_model_name"] = data["writing_model_name"]
        app_state["writing_model_name"] = data["writing_model_name"]
    if "writing_custom_type" in data:
        updates["writing_custom_type"] = data["writing_custom_type"]
        app_state["writing_custom_type"] = data["writing_custom_type"]
    if "writing_custom_ollama_model" in data:
        updates["writing_custom_ollama_model"] = data["writing_custom_ollama_model"]
        app_state["writing_custom_ollama_model"] = data["writing_custom_ollama_model"]
    if "writing_custom_online_model" in data:
        updates["writing_custom_online_model"] = data["writing_custom_online_model"]
        app_state["writing_custom_online_model"] = data["writing_custom_online_model"]

    # 模型参数 (temperature, top_p, etc.)
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

    # UI 设置 (保存到配置文件)
    ui_setting_keys = ["show_typing_animation", "typing_speed", "enable_keyboard_shortcuts"]
    for key in ui_setting_keys:
        if key in data:
            updates[key] = data[key]
            app_state[key] = data[key]

    config_manager.update_api_config(DATA_DIR, updates)
    init_llm_client()  # 应用新配置

    return jsonify({'success': True, 'message': 'API配置已更新'})


@app.route('/api/refresh_ollama_models', methods=['POST'])
def refresh_ollama_models():
    data = request.json
    api_url = data.get('api_url', app_state.get("ollama_api_url"))

    if not api_url:
        return jsonify({'success': False, 'error': 'Ollama API URL不能为空'})
    try:
        temp_client = OllamaClient(api_url=api_url, default_model="any")
        models_data = temp_client.list_local_models()
        if models_data is not None:
            model_names = [m.get("name") for m in models_data if m.get("name")]
            app_state["available_ollama_models"] = model_names
            # 将获取到的模型列表也保存到配置文件中
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

    if not app_state.get("llm_client"):
        init_llm_client()
        if not app_state.get("llm_client"):
            return jsonify({'success': False, 'error': 'LLM客户端未能初始化，请检查API配置'})

    current_llm_client = app_state["llm_client"]
    # 获取当前为测试选择的LLM参数
    current_api_config = config_manager.load_api_configs(DATA_DIR)
    model_params_for_test = config_manager.get_model_params(current_api_config)

    try:
        response_data = current_llm_client.generate_chat_completion(
            model=current_llm_client.default_model,  # 测试时使用客户端的默认模型
            messages=[
                {"role": "system", "content": "你是一个有用的AI助手。"},
                {"role": "user", "content": test_message}
            ],
            options=model_params_for_test  # 传递当前配置的参数
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

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    novel_base_name_for_dir = utils.sanitize_filename(novel_title if novel_title else "untitled_novel")
    per_novel_upload_dir_name = f"{timestamp}_{novel_base_name_for_dir}_{unique_id}"
    novel_data_dir = os.path.join(DATA_DIR, per_novel_upload_dir_name)
    os.makedirs(novel_data_dir, exist_ok=True)
    file_path_in_data_dir = os.path.join(novel_data_dir, secure_filename(file.filename))
    file.seek(0)
    file.save(file_path_in_data_dir)

    app_state["app_stage"] = "processing"
    app_state["novel_title"] = novel_title
    app_state["novel_data_dir"] = novel_data_dir
    app_state["chapters_dir"] = os.path.join(novel_data_dir, 'chapters')
    app_state["analysis_path"] = os.path.join(novel_data_dir, 'final_analysis.json')
    app_state["novel_specific_data_dir_ui"] = novel_data_dir
    app_state["chapters_data_path_ui"] = app_state["chapters_dir"]  # UI显示用
    app_state["final_analysis_path_ui"] = app_state["analysis_path"]  # UI显示用

    if not app_state.get("llm_client"):
        init_llm_client()
        if not app_state.get("llm_client"):
            app_state["app_stage"] = "config_novel"
            return jsonify({'success': False, 'error': 'LLM客户端初始化失败，请检查API配置后再上传。'})

    # 为 NovelProcessor 确定分析模型
    # NovelProcessor 将使用 app_state["llm_client"]，但其内部调用 generate_chat_completion 时可以指定 model
    # 我们需要根据分析模型的配置来决定传递给 NovelProcessor 的 llm_client 的 default_model 或特定模型名

    current_api_config = config_manager.load_api_configs(DATA_DIR)
    analysis_model_to_use_for_processor = app_state["llm_client"].default_model  # 默认用主客户端模型

    if current_api_config.get("analysis_model_name") == "custom":
        if app_state["llm_client"].client_type == "ollama" and current_api_config.get(
                "analysis_custom_type") == "ollama":
            analysis_model_to_use_for_processor = current_api_config.get("analysis_custom_ollama_model",
                                                                         app_state["llm_client"].default_model)
        elif app_state["llm_client"].client_type == "online_api" and current_api_config.get(
                "analysis_custom_type") == "online":
            analysis_model_to_use_for_processor = current_api_config.get("analysis_custom_online_model",
                                                                         app_state["llm_client"].default_model)
    elif current_api_config.get("analysis_model_name") != "custom":  # 预设模型
        # 如果是预设模型，并且与当前客户端类型匹配，则使用该预设名
        # 假设预设名可以直接作为模型标识符
        if app_state["llm_client"].client_type == "ollama" and not current_api_config.get("use_online_api"):
            analysis_model_to_use_for_processor = current_api_config.get("analysis_model_name")  # 例如 "llama3"
        elif app_state["llm_client"].client_type == "online_api" and current_api_config.get("use_online_api"):
            analysis_model_to_use_for_processor = current_api_config.get("analysis_model_name")

    # 创建一个新的LLM Client实例专门用于分析，如果分析模型与主客户端模型不同
    # 或者修改 NovelProcessor 使其能接受特定的model_name参数传递给llm_client.generate_chat_completion
    # 当前 NovelProcessor 直接使用传入的 llm_client 及其 default_model
    # 为简单起见，如果分析模型与主写作模型不同，我们这里可以临时改变主客户端的 default_model，用完再改回去
    # 或者，更好的方式是 NovelProcessor 的 _call_llm_for_analysis_raw_json 方法能够接受一个 model_name 参数

    # 临时的解决方案: 如果分析模型与写作模型不同，且客户端类型相同，可以尝试创建一个临时客户端
    # 但更稳妥的是让 NovelProcessor 的调用方法支持指定模型。
    # 目前 NovelProcessor.py 中的 _call_llm_for_analysis_raw_json 使用 self.llm_client.default_model
    # 所以，如果分析模型和写作模型不同，需要确保 llm_client 在 NovelProcessor 使用前 default_model 正确
    # 或者 NovelProcessor 内部能选择模型。

    # 假设 NovelProcessor 使用传入的 llm_client 的 default_model
    # 我们需要确保这个 default_model 是分析模型。
    # 如果分析模型和写作模型不同，这里可能需要一个独立的分析用LLM客户端实例。
    # 简化：我们先用主llm_client，其default_model已根据写作模型设置。
    # 如果要严格区分，需要调整NovelProcessor或LLMClient的交互。

    # 传递给NovelProcessor的llm_client应该是配置了正确分析模型的客户端
    # 如果分析模型和写作模型不同，这里需要决策。
    # 假设：如果分析模型与主客户端（写作模型客户端）的类型和模型都不同，则需要一个单独的实例。
    # 为了演示，我们暂时让 NovelProcessor 使用 app_state["llm_client"]，并假设其 default_model 适用于分析。
    # 实际应用中，如果分析和写作模型差异很大，应该用不同的客户端实例或可切换模型的客户端。

    novel_processor = NovelProcessor(
        llm_client=app_state["llm_client"],  # NovelProcessor 会使用这个客户端的 default_model
        novel_file_path=file_path_in_data_dir,
        output_dir=novel_data_dir
    )
    # 如果希望 NovelProcessor 使用特定的分析模型，而不是 llm_client 的 default_model，
    # 需要修改 NovelProcessor 的 _call_llm_for_analysis_raw_json 方法，使其接受 model_name 参数，
    # 或者在创建 NovelProcessor 时传入一个专门为分析配置的 llm_client 实例。

    success = novel_processor.process_novel()

    if success:
        final_analysis = utils.read_json_file(app_state["analysis_path"])
        if final_analysis:
            app_state["app_stage"] = "initializing_narrative"
            app_state["novel_title"] = final_analysis.get("title", novel_title)
            if "excerpts" in final_analysis and final_analysis["excerpts"]:
                app_state["novel_excerpt"] = final_analysis["excerpts"][0].get("text", "暂无精选片段")
            else:
                app_state["novel_excerpt"] = "分析完成，但未找到精选片段。"
            if "world_building" in final_analysis and final_analysis["world_building"]:
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

    if not app_state.get("llm_client"):  # 主客户端（通常是写作模型客户端）
        init_llm_client()
        if not app_state.get("llm_client"):
            return jsonify({'success': False, 'error': 'LLM客户端初始化失败，无法开始叙事。'})

    current_api_config = config_manager.load_api_configs(DATA_DIR)
    model_params = config_manager.get_model_params(current_api_config)

    # NarrativeEngine 使用的 model_name 应该是写作模型的名称
    # app_state["llm_client"] 已经根据写作模型配置初始化
    writing_model_for_engine = app_state["llm_client"].default_model

    app_state["narrative_engine"] = NarrativeEngine(
        llm_client=app_state["llm_client"],  # 传递主客户端实例
        novel_data_dir=app_state["novel_data_dir"],
        chapters_dir=app_state["chapters_dir"],
        analysis_path=app_state["analysis_path"],
        model_name=writing_model_for_engine,  # 引擎记录它被初始化时使用的模型
        saved_state=app_state.get("engine_state_to_load")
    )
    app_state["engine_state_to_load"] = None

    initial_narrative = app_state["narrative_engine"].initialize_narrative_session(
        initial_context_chapters=current_api_config.get("initial_context_chapters", 3),
        window_before=current_api_config.get("window_before", 2),
        window_after=current_api_config.get("window_after", 2),
        divergence_threshold=current_api_config.get("divergence_threshold", 0.7),
        model_params=model_params
    )

    if initial_narrative is not None:
        app_state["app_stage"] = "narrating"
        app_state["narrative_history_display"] = []
        if hasattr(app_state["narrative_engine"], 'conversation_history'):
            for entry in app_state["narrative_engine"].conversation_history:
                speaker = "用户" if entry.get("role") == "user" else ("系统" if entry.get("role") == "system" else "AI")
                app_state["narrative_history_display"].append((speaker, entry.get("content", "")))
        return jsonify({'success': True, 'initial_narrative': initial_narrative})
    else:
        error_msg = "初始化叙事会话失败。"
        if hasattr(app_state["narrative_engine"], 'last_error') and app_state["narrative_engine"].last_error:
            error_msg += f" 详情: {app_state['narrative_engine'].last_error}"
        app_state["narrative_engine"] = None
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
        app_state["narrative_history_display"] = []
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

    save_path = app_state["narrative_engine"].save_state_to_file()

    if save_path:
        # --- 开始修改：同时创建历史记录 ---
        current_api_config = config_manager.load_api_configs(DATA_DIR)
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
            "selected_ollama_model": current_api_config.get("selected_ollama_model"),
            "online_api_model": current_api_config.get("online_api_model"),
            "analysis_model_name_ui": app_state.get("analysis_model_name"),  # UI选择的分析模型名
            "writing_model_name_ui": app_state.get("writing_model_name"),  # UI选择的写作模型名
            # 注意：API Key 不应保存到历史记录中
        }

        history_path = history_manager.save_current_conversation(
            data_dir=DATA_DIR,
            narrative_engine=app_state["narrative_engine"],
            novel_name=app_state.get("novel_title", "未知小说"),
            app_config=app_config_for_history
        )
        # --- 结束修改 ---

        if history_path:
            app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)  # 刷新历史列表
            return jsonify({'success': True, 'save_path': save_path, 'history_path': history_path,
                            'message': '游戏已保存，并已创建历史对话记录！'})
        else:
            # 游戏状态保存成功，但历史记录创建失败
            return jsonify({'success': True, 'save_path': save_path, 'history_path': None,
                            'message': '游戏已保存，但创建历史对话记录失败。'})
    else:
        return jsonify({'success': False, 'error': '保存游戏状态失败'})


@app.route('/load_game', methods=['POST'])
def load_game():
    data = request.json
    save_path = data.get('save_path', '')  # 这个 save_path 是来自 saves 目录的存档

    if not save_path or not os.path.exists(save_path):
        return jsonify({'success': False, 'error': '存档路径无效或文件不存在'})

    # save_manager.load_game_state 只是简单读取JSON
    loaded_state_from_save_file = utils.read_json_file(save_path)

    if loaded_state_from_save_file:
        # NarrativeEngine 的构造函数期望的是 get_state_for_saving() 的输出格式
        # 这个格式直接就是存档文件的内容
        app_state["engine_state_to_load"] = loaded_state_from_save_file

        # 从存档数据中恢复关键路径信息到 app_state
        app_state["novel_data_dir"] = loaded_state_from_save_file.get("novel_data_dir", "")
        app_state["chapters_dir"] = loaded_state_from_save_file.get("chapters_dir", "")
        app_state["analysis_path"] = loaded_state_from_save_file.get("analysis_path", "")

        app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
        app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
        app_state["final_analysis_path_ui"] = app_state["analysis_path"]

        # 尝试加载并显示小说基本信息 (从分析文件)
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

        # 还需要根据存档中的模型信息等恢复API配置（如果存档中包含这些）
        # 当前的 save_state_to_file 保存了 model_name，可以用来尝试恢复
        # 但更完整的配置恢复可能需要从历史记录加载时的逻辑
        # 为了简化，这里假设API配置通过UI或历史记录加载来管理

        app_state["app_stage"] = "initializing_narrative"
        return jsonify({'success': True, 'message': '游戏存档已加载，准备开始旅程。'})
    else:
        return jsonify({'success': False, 'error': '加载游戏状态失败'})


@app.route('/api/saves/list', methods=['GET'])
def get_saves_list_route():
    if not app_state.get("novel_data_dir") or not os.path.exists(app_state["novel_data_dir"]):
        return jsonify({'success': True, 'saves': [], 'message': '当前无激活小说，无法列出存档。'})
    saves = save_manager.get_saves_list(app_state["novel_data_dir"])
    return jsonify({'success': True, 'saves': saves})


@app.route('/api/history/list', methods=['GET'])
def get_history_list_route():
    history_list = history_manager.load_history_conversations(DATA_DIR)
    app_state["history_conversations"] = history_list
    return jsonify({'success': True, 'history': history_list})


@app.route('/api/history/save', methods=['POST'])
def save_history_route():
    if app_state.get("app_stage") != "narrating" or not app_state.get("narrative_engine"):
        return jsonify({'success': False, 'error': '当前无正在进行的叙事，无法保存到历史。'})

    current_api_config = config_manager.load_api_configs(DATA_DIR)
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
        "selected_ollama_model": current_api_config.get("selected_ollama_model"),
        "online_api_model": current_api_config.get("online_api_model"),
        "analysis_model_name_ui": app_state.get("analysis_model_name"),
        "writing_model_name_ui": app_state.get("writing_model_name"),
    }
    history_path = history_manager.save_current_conversation(
        data_dir=DATA_DIR,
        narrative_engine=app_state["narrative_engine"],
        novel_name=app_state.get("novel_title", "未知小说"),
        app_config=app_config_for_history
    )
    if history_path:
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
        return jsonify({'success': True, 'history_path': history_path, 'message': '当前对话已保存到历史记录。'})
    else:
        return jsonify({'success': False, 'error': '保存历史对话失败'})


@app.route('/api/history/delete', methods=['POST'])
def delete_history_route():
    data = request.json
    file_path = data.get('file_path', '')
    if not file_path:
        return jsonify({'success': False, 'error': '未提供文件路径'})
    # 安全性考虑：应确保 file_path 在预期的 HISTORY_DIR 内
    # full_path = os.path.normpath(os.path.join(DATA_DIR, history_manager.HISTORY_DIR, os.path.basename(file_path)))
    # expected_dir = os.path.normpath(os.path.join(DATA_DIR, history_manager.HISTORY_DIR))
    # if not full_path.startswith(expected_dir) or not os.path.exists(full_path):
    #     return jsonify({'success': False, 'error': '历史对话文件路径无效或不安全'})
    # 简化：假设前端提供的路径是可信的（在 history_manager.load_history_conversations 中已验证存在）

    success = history_manager.delete_history_conversation(file_path)  # 直接使用前端提供的完整路径
    if success:
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
        return jsonify({'success': True, 'message': '历史对话已删除。'})
    else:
        return jsonify({'success': False, 'error': '删除历史对话失败'})


@app.route('/api/history/load', methods=['POST'])
def load_history_route():
    data = request.json
    file_path = data.get('file_path', '')
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

            config_updates = {}
            for key, value in loaded_app_config.items():
                if key in app_state: app_state[key] = value
                # 检查是否是 config_manager 管理的键
                # config_manager.load_api_configs(DATA_DIR) 返回的是完整的配置字典
                # 我们只更新那些存在于默认配置结构中的键，以避免写入不相关的历史数据
                if key in config_manager.load_api_configs(DATA_DIR):
                    config_updates[key] = value

            if config_updates:
                config_manager.update_api_config(DATA_DIR, config_updates)

            init_llm_client()
            if not app_state.get("llm_client"):
                return jsonify({'success': False, 'error': '根据历史记录配置LLM客户端失败。'})

            app_state["engine_state_to_load"] = engine_state_to_load
            if engine_state_to_load:
                app_state["novel_data_dir"] = engine_state_to_load.get("novel_data_dir", "")
                app_state["chapters_dir"] = engine_state_to_load.get("chapters_dir", "")
                app_state["analysis_path"] = engine_state_to_load.get("analysis_path", "")
                app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
                app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
                app_state["final_analysis_path_ui"] = app_state["analysis_path"]

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
                elif "metadata" in history_item_data and "novel_name" in history_item_data["metadata"]:
                    app_state["novel_title"] = history_item_data["metadata"]["novel_name"]

            app_state["app_stage"] = "initializing_narrative"
            return jsonify({'success': True, 'message': '历史对话已加载，小说信息已更新，准备开始旅程。'})
        else:
            return jsonify({'success': False, 'error': result.get("error", "从历史记录提取对话数据失败。")})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'加载历史对话时发生意外错误: {str(e)}'})


@app.route('/api/config/reset', methods=['POST'])
def reset_config_route():
    default_config = config_manager.reset_api_config(DATA_DIR)
    for key, value in default_config.items():
        if key in app_state:
            app_state[key] = value
    init_llm_client()
    return jsonify({'success': True, 'message': 'API及应用配置已重置为默认值。'})


@app.route('/update_settings', methods=['POST'])
def update_settings_route():
    data = request.json
    updates_for_config_file = {}

    ui_setting_keys = ["show_typing_animation", "typing_speed", "enable_keyboard_shortcuts"]
    for key in ui_setting_keys:
        if key in data:
            app_state[key] = data[key]
            updates_for_config_file[key] = data[key]  # 这些也保存到配置

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
        # 如果更新了影响LLM客户端的参数（如temperature），可能需要重新初始化或确保客户端能动态使用这些参数
        # init_llm_client() # 当前的LLM客户端在generate_chat_completion时会接收options参数，所以不一定需要重初始化

    return jsonify({'success': True, 'message': '设置已更新。'})


@app.route('/reset_journey', methods=['POST'])
def reset_journey_route():
    reset_for_new_journey()
    return jsonify({'success': True, 'message': '应用已重置，可以开始新的旅程。'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
