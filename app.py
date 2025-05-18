from flask import Flask, render_template, request, jsonify
import os
import json
import time
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid
import shutil

# 导入自定义模块
from novel_processor import NovelProcessor
from narrative_engine import NarrativeEngine
import history_manager
import save_manager
import config_manager
import utils
from llm_client import LLMClient

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
    app_state["ollama_api_url_config"] = api_config.get("ollama_api_url", "http://127.0.0.1:11434")  # 兼容前端
    app_state["selected_ollama_model"] = api_config.get("selected_ollama_model", "gemma3:12b-it-q8_0")
    app_state["online_api_url"] = api_config.get("online_api_url", "")
    app_state["online_api_model"] = api_config.get("online_api_model", "")
    app_state["online_api_key"] = api_config.get("online_api_key", "")
    app_state["analysis_model_name"] = api_config.get("analysis_model_name", "llama3")
    app_state["writing_model_name"] = api_config.get("writing_model_name", "llama3")
    app_state["available_ollama_models"] = api_config.get("available_ollama_models", ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0"])

    # 应用阶段
    app_state["app_stage"] = "config_novel"  # config_novel, processing, initializing_narrative, narrating

    # 小说数据
    app_state["novel_title"] = ""
    app_state["novel_excerpt"] = ""
    app_state["world_setting"] = ""
    app_state["character_info"] = None

    # 历史对话
    app_state["history_conversations"] = []
    app_state["show_history_panel"] = True

    # 叙事历史
    app_state["narrative_history"] = []
    app_state["narrative_history_display"] = []  # 兼容前端

    # 叙事引擎
    app_state["narrative_engine"] = None
    app_state["engine_state_to_load"] = None

    # 小说分析路径
    app_state["novel_data_dir"] = ""
    app_state["chapters_dir"] = ""
    app_state["analysis_path"] = ""
    app_state["novel_specific_data_dir_ui"] = ""  # 兼容前端
    app_state["chapters_data_path_ui"] = ""  # 兼容前端
    app_state["final_analysis_path_ui"] = ""  # 兼容前端

    # 叙事窗口设置
    app_state["initial_context_chapters"] = api_config.get("initial_context_chapters", 3)
    app_state["window_before"] = api_config.get("window_before", 2)
    app_state["window_after"] = api_config.get("window_after", 2)
    app_state["narrative_window_chapter_before"] = api_config.get("window_before", 2)  # 兼容前端
    app_state["narrative_window_chapter_after"] = api_config.get("window_after", 2)  # 兼容前端
    app_state["divergence_threshold"] = api_config.get("divergence_threshold", 0.7)

    # 模型参数
    app_state["temperature"] = api_config.get("temperature", 0.7)
    app_state["top_p"] = api_config.get("top_p", 0.9)
    app_state["max_tokens"] = api_config.get("max_tokens", 1024)
    app_state["frequency_penalty"] = api_config.get("frequency_penalty", 0.0)
    app_state["presence_penalty"] = api_config.get("presence_penalty", 0.0)

    # UI设置
    app_state["show_typing_animation"] = True
    app_state["typing_speed"] = 50
    app_state["enable_keyboard_shortcuts"] = True

    # LLM客户端
    app_state["llm_client"] = None
    app_state["analysis_llm_client"] = None  # 兼容前端
    app_state["writing_llm_client"] = None  # 兼容前端

# 重置应用状态以准备新的旅程
def reset_for_new_journey():
    # 保留API配置和UI设置
    api_config = {
        "use_online_api": app_state.get("use_online_api", False),
        "ollama_api_url": app_state.get("ollama_api_url", "http://127.0.0.1:11434"),
        "selected_ollama_model": app_state.get("selected_ollama_model", "gemma3:12b-it-q8_0"),
        "online_api_url": app_state.get("online_api_url", ""),
        "online_api_model": app_state.get("online_api_model", ""),
        "online_api_key": app_state.get("online_api_key", ""),
        "analysis_model_name": app_state.get("analysis_model_name", "llama3"),
        "writing_model_name": app_state.get("writing_model_name", "llama3"),
        "available_ollama_models": app_state.get("available_ollama_models", []),
        "temperature": app_state.get("temperature", 0.7),
        "top_p": app_state.get("top_p", 0.9),
        "max_tokens": app_state.get("max_tokens", 1024),
        "frequency_penalty": app_state.get("frequency_penalty", 0.0),
        "presence_penalty": app_state.get("presence_penalty", 0.0),
        "initial_context_chapters": app_state.get("initial_context_chapters", 3),
        "window_before": app_state.get("window_before", 2),
        "window_after": app_state.get("window_after", 2),
        "divergence_threshold": app_state.get("divergence_threshold", 0.7)
    }

    # 保留UI设置
    ui_settings = {
        "show_typing_animation": app_state.get("show_typing_animation", True),
        "typing_speed": app_state.get("typing_speed", 50),
        "enable_keyboard_shortcuts": app_state.get("enable_keyboard_shortcuts", True)
    }

    # 重新初始化应用状态
    init_app_state()

    # 恢复API配置
    for key, value in api_config.items():
        if key in app_state:
            app_state[key] = value

    # 恢复UI设置
    for key, value in ui_settings.items():
        if key in app_state:
            app_state[key] = value

# 初始化LLM客户端
def init_llm_client():
    if app_state["use_online_api"]:
        # 使用在线API
        app_state["llm_client"] = LLMClient(
            client_type="online",
            api_url=app_state["online_api_url"],
            api_key=app_state["online_api_key"],
            model_name=app_state["online_api_model"]
        )
    else:
        # 使用Ollama
        app_state["llm_client"] = LLMClient(
            client_type="ollama",
            api_url=app_state["ollama_api_url"],
            model_name=app_state["selected_ollama_model"]
        )
    
    # 兼容前端
    app_state["analysis_llm_client"] = app_state["llm_client"]
    app_state["writing_llm_client"] = app_state["llm_client"]

# 初始化应用状态
init_app_state()

@app.route('/')
def index():
    return render_template('index.html', app_state=app_state)

@app.route('/api/update_api_config', methods=['POST'])
def update_api_config():
    data = request.json

    # 更新API配置
    updates = {}
    
    # 基本配置
    if "use_online_api" in data:
        updates["use_online_api"] = data["use_online_api"]
    
    # Ollama API配置
    if "ollama_api_url" in data:
        updates["ollama_api_url"] = data["ollama_api_url"]
        app_state["ollama_api_url_config"] = data["ollama_api_url"]  # 兼容前端
    
    if "selected_ollama_model" in data:
        updates["selected_ollama_model"] = data["selected_ollama_model"]
    
    # 在线API配置
    if "online_api_url" in data:
        updates["online_api_url"] = data["online_api_url"]
    
    if "online_api_model" in data:
        updates["online_api_model"] = data["online_api_model"]
    
    if "online_api_key" in data:
        updates["online_api_key"] = data["online_api_key"]
    
    # 模型配置
    if "analysis_model_name" in data:
        updates["analysis_model_name"] = data["analysis_model_name"]
    
    if "writing_model_name" in data:
        updates["writing_model_name"] = data["writing_model_name"]
    
    # 模型参数
    if "temperature" in data:
        updates["temperature"] = data["temperature"]
    
    if "top_p" in data:
        updates["top_p"] = data["top_p"]
    
    if "max_tokens" in data:
        updates["max_tokens"] = data["max_tokens"]
    
    if "frequency_penalty" in data:
        updates["frequency_penalty"] = data["frequency_penalty"]
    
    if "presence_penalty" in data:
        updates["presence_penalty"] = data["presence_penalty"]
    
    # 叙事窗口设置
    if "initial_context_chapters" in data:
        updates["initial_context_chapters"] = data["initial_context_chapters"]
    
    if "window_before" in data:
        updates["window_before"] = data["window_before"]
        app_state["narrative_window_chapter_before"] = data["window_before"]  # 兼容前端
    
    if "window_after" in data:
        updates["window_after"] = data["window_after"]
        app_state["narrative_window_chapter_after"] = data["window_after"]  # 兼容前端
    
    if "divergence_threshold" in data:
        updates["divergence_threshold"] = data["divergence_threshold"]

    # 更新配置
    updated_config = config_manager.update_api_config(DATA_DIR, updates)
    
    # 更新应用状态
    for key, value in updated_config.items():
        if key in app_state:
            app_state[key] = value
    
    # 重新初始化LLM客户端
    init_llm_client()
    
    return jsonify({'success': True})

@app.route('/api/refresh_ollama_models', methods=['POST'])
def refresh_ollama_models():
    data = request.json
    api_url = data.get('api_url', '')

    if not api_url:
        return jsonify({'success': False, 'error': 'API URL不能为空'})

    try:
        # 创建临时客户端
        temp_client = LLMClient(client_type="ollama", api_url=api_url)
        
        # 获取可用模型
        models = temp_client.get_available_models()
        
        if models:
            # 更新应用状态和API配置
            app_state["available_ollama_models"] = models
            
            # 更新配置
            config_manager.update_api_config(DATA_DIR, {"available_ollama_models": models})
            
            return jsonify({'success': True, 'models': models})
        else:
            return jsonify({'success': False, 'error': '获取模型列表失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'获取模型列表出错: {str(e)}'})

@app.route('/api/test_api', methods=['POST'])
def test_api():
    data = request.json
    test_message = data.get('message', '')

    if not test_message:
        return jsonify({'success': False, 'error': '测试消息不能为空'})

    try:
        # 初始化LLM客户端
        init_llm_client()
        
        if not app_state["llm_client"]:
            return jsonify({'success': False, 'error': '创建LLM客户端失败'})
        
        # 发送测试消息
        response = app_state["llm_client"].chat_completion([
            {"role": "system", "content": "你是一个有用的AI助手。"},
            {"role": "user", "content": test_message}
        ])
        
        if response:
            return jsonify({'success': True, 'response': response})
        else:
            return jsonify({'success': False, 'error': '获取API响应失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'测试API出错: {str(e)}'})

@app.route('/upload_novel', methods=['POST'])
def upload_novel():
    # 检查是否有文件
    if 'novel_file' not in request.files:
        return jsonify({'success': False, 'error': '没有找到文件'})

    file = request.files['novel_file']

    # 检查文件名
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})

    # 检查文件类型
    if not file.filename.endswith('.txt'):
        return jsonify({'success': False, 'error': '只支持TXT格式的文件'})

    # 获取小说标题
    novel_title = request.form.get('novel_title', '')
    if not novel_title:
        novel_title = os.path.splitext(file.filename)[0]

    # 安全的文件名
    filename = secure_filename(file.filename)

    # 创建唯一的上传路径
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"{timestamp}_{unique_id}")
    os.makedirs(upload_dir, exist_ok=True)

    # 保存文件
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    # 更新应用状态
    app_state["app_stage"] = "processing"
    app_state["novel_title"] = novel_title

    # 创建小说特定的数据目录
    novel_data_dir = os.path.join(DATA_DIR, f"{timestamp}_{unique_id}")
    os.makedirs(novel_data_dir, exist_ok=True)

    # 更新应用状态中的路径
    app_state["novel_data_dir"] = novel_data_dir
    app_state["chapters_dir"] = os.path.join(novel_data_dir, 'chapters')
    app_state["analysis_path"] = os.path.join(novel_data_dir, 'final_analysis.json')
    
    # 兼容前端
    app_state["novel_specific_data_dir_ui"] = novel_data_dir
    app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
    app_state["final_analysis_path_ui"] = app_state["analysis_path"]

    # 初始化LLM客户端
    init_llm_client()

    # 创建小说处理器
    novel_processor = NovelProcessor(
        app_state["llm_client"],
        file_path,
        novel_data_dir
    )

    # 处理小说
    success = novel_processor.process_novel()

    if success:
        # 加载分析结果
        final_analysis = utils.read_json_file(app_state["analysis_path"])

        if final_analysis:
            # 更新应用状态
            app_state["app_stage"] = "initializing_narrative"

            # 提取精选片段
            if "excerpts" in final_analysis and len(final_analysis["excerpts"]) > 0:
                app_state["novel_excerpt"] = final_analysis["excerpts"][0]["text"]

            # 提取世界设定
            if "world_building" in final_analysis and len(final_analysis["world_building"]) > 0:
                app_state["world_setting"] = final_analysis["world_building"][0]["description"]

            # 提取人物信息
            if "characters" in final_analysis and len(final_analysis["characters"]) > 0:
                app_state["character_info"] = {
                    "name": final_analysis["characters"][0]["name"],
                    "description": final_analysis["characters"][0]["description"]
                }

            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '加载分析结果失败'})
    else:
        return jsonify({'success': False, 'error': '处理小说失败'})

@app.route('/start_narrative', methods=['POST'])
def start_narrative():
    # 检查应用状态
    if app_state["app_stage"] != "initializing_narrative":
        return jsonify({'success': False, 'error': '应用状态不正确'})

    # 获取模型参数
    model_params = config_manager.get_model_params(config_manager.load_api_configs(DATA_DIR))

    # 创建叙事引擎
    app_state["narrative_engine"] = NarrativeEngine(
        app_state["llm_client"],
        app_state["novel_data_dir"],
        app_state["chapters_dir"],
        app_state["analysis_path"],
        app_state["writing_model_name"],
        app_state.get("engine_state_to_load")
    )

    # 初始化叙事会话
    initial_narrative = app_state["narrative_engine"].initialize_narrative_session(
        app_state["initial_context_chapters"],
        app_state["window_before"],
        app_state["window_after"],
        app_state["divergence_threshold"],
        model_params
    )

    if initial_narrative:
        # 更新应用状态
        app_state["app_stage"] = "narrating"
        app_state["narrative_history"] = app_state["narrative_engine"].conversation_history
        
        # 兼容前端
        app_state["narrative_history_display"] = []
        for entry in app_state["narrative_history"]:
            if entry["role"] == "user":
                app_state["narrative_history_display"].append(("用户", entry["content"]))
            else:
                app_state["narrative_history_display"].append(("系统", entry["content"]))

        return jsonify({'success': True, 'initial_narrative': initial_narrative})
    else:
        return jsonify({'success': False, 'error': '初始化叙事会话失败'})

@app.route('/process_action', methods=['POST'])
def process_action():
    data = request.json
    user_action = data.get('action', '')

    if not user_action:
        return jsonify({'success': False, 'error': '用户行动不能为空'})

    # 检查应用状态
    if app_state["app_stage"] != "narrating" or not app_state["narrative_engine"]:
        return jsonify({'success': False, 'error': '应用状态不正确或叙事引擎未初始化'})

    # 获取模型参数
    model_params = config_manager.get_model_params(config_manager.load_api_configs(DATA_DIR))

    # 处理用户行动
    response = app_state["narrative_engine"].process_user_action(user_action, model_params)

    if response:
        # 更新应用状态
        app_state["narrative_history"] = app_state["narrative_engine"].conversation_history
        
        # 兼容前端
        app_state["narrative_history_display"] = []
        for entry in app_state["narrative_history"]:
            if entry["role"] == "user":
                app_state["narrative_history_display"].append(("用户", entry["content"]))
            else:
                app_state["narrative_history_display"].append(("系统", entry["content"]))

        return jsonify({'success': True, 'response': response})
    else:
        return jsonify({'success': False, 'error': '处理用户行动失败'})

@app.route('/save_game', methods=['POST'])
def save_game():
    # 检查应用状态
    if app_state["app_stage"] != "narrating" or not app_state["narrative_engine"]:
        return jsonify({'success': False, 'error': '应用状态不正确或叙事引擎未初始化'})

    # 保存游戏状态
    save_path = save_manager.save_game_state(app_state["narrative_engine"], app_state["novel_data_dir"])

    if save_path:
        return jsonify({'success': True, 'save_path': save_path})
    else:
        return jsonify({'success': False, 'error': '保存游戏状态失败'})

@app.route('/load_game', methods=['POST'])
def load_game():
    data = request.json
    save_path = data.get('save_path', '')

    if not save_path or not os.path.exists(save_path):
        return jsonify({'success': False, 'error': '存档路径无效'})

    # 加载游戏状态
    save_data = save_manager.load_game_state(save_path)

    if save_data:
        # 保存引擎状态以便后续初始化
        app_state["engine_state_to_load"] = save_data
        
        # 更新应用状态
        app_state["app_stage"] = "initializing_narrative"
        app_state["novel_data_dir"] = save_data.get("novel_data_dir", "")
        app_state["chapters_dir"] = save_data.get("chapters_dir", "")
        app_state["analysis_path"] = save_data.get("analysis_path", "")
        
        # 兼容前端
        app_state["novel_specific_data_dir_ui"] = app_state["novel_data_dir"]
        app_state["chapters_data_path_ui"] = app_state["chapters_dir"]
        app_state["final_analysis_path_ui"] = app_state["analysis_path"]
        
        # 加载分析结果
        if os.path.exists(app_state["analysis_path"]):
            final_analysis = utils.read_json_file(app_state["analysis_path"])
            
            if final_analysis:
                app_state["novel_title"] = final_analysis.get("title", "未知小说")
                
                # 提取精选片段
                if "excerpts" in final_analysis and len(final_analysis["excerpts"]) > 0:
                    app_state["novel_excerpt"] = final_analysis["excerpts"][0]["text"]
                
                # 提取世界设定
                if "world_building" in final_analysis and len(final_analysis["world_building"]) > 0:
                    app_state["world_setting"] = final_analysis["world_building"][0]["description"]
                
                # 提取人物信息
                if "characters" in final_analysis and len(final_analysis["characters"]) > 0:
                    app_state["character_info"] = {
                        "name": final_analysis["characters"][0]["name"],
                        "description": final_analysis["characters"][0]["description"]
                    }
        
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '加载游戏状态失败'})

@app.route('/api/saves/list', methods=['GET'])
def get_saves_list():
    # 检查是否有小说数据目录
    if not app_state["novel_data_dir"] or not os.path.exists(app_state["novel_data_dir"]):
        return jsonify({'success': False, 'error': '小说数据目录不存在'})

    # 获取存档列表
    saves = save_manager.get_saves_list(app_state["novel_data_dir"])
    
    return jsonify({'success': True, 'saves': saves})

@app.route('/api/history/list', methods=['GET'])
def get_history_list():
    # 获取历史对话列表
    history_list = history_manager.load_history_conversations(DATA_DIR)
    
    # 更新应用状态
    app_state["history_conversations"] = history_list
    
    return jsonify({'success': True, 'history': history_list})

@app.route('/api/history/save', methods=['POST'])
def save_history():
    # 检查应用状态
    if app_state["app_stage"] != "narrating" or not app_state["narrative_engine"]:
        return jsonify({'success': False, 'error': '应用状态不正确或叙事引擎未初始化'})

    # 获取应用配置
    app_config = {
        "temperature": app_state["temperature"],
        "top_p": app_state["top_p"],
        "max_tokens": app_state["max_tokens"],
        "frequency_penalty": app_state["frequency_penalty"],
        "presence_penalty": app_state["presence_penalty"],
        "initial_context_chapters": app_state["initial_context_chapters"],
        "window_before": app_state["window_before"],
        "window_after": app_state["window_after"],
        "divergence_threshold": app_state["divergence_threshold"],
        "selected_analysis_model": app_state["analysis_model_name"],
        "writing_model_source": "Local Ollama" if not app_state["use_online_api"] else "Online API"
    }

    # 保存当前对话
    history_path = history_manager.save_current_conversation(
        DATA_DIR,
        app_state["narrative_engine"],
        app_state["novel_title"],
        app_config
    )

    if history_path:
        # 刷新历史对话列表
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
        
        return jsonify({'success': True, 'history_path': history_path})
    else:
        return jsonify({'success': False, 'error': '保存历史对话失败'})

@app.route('/api/history/delete', methods=['POST'])
def delete_history():
    data = request.json
    file_path = data.get('file_path', '')

    if not file_path or not os.path.exists(file_path):
        return jsonify({'success': False, 'error': '历史对话文件路径无效'})

    # 删除历史对话
    success = history_manager.delete_history_conversation(file_path)
    
    if success:
        # 刷新历史对话列表
        app_state["history_conversations"] = history_manager.load_history_conversations(DATA_DIR)
        
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '删除历史对话失败'})

@app.route('/api/history/load', methods=['POST'])
def load_history():
    data = request.json
    file_path = data.get('file_path', '')

    if not file_path or not os.path.exists(file_path):
        return jsonify({'success': False, 'error': '历史对话文件路径无效'})

    try:
        # 加载历史对话
        history_data = utils.read_json_file(file_path)
        
        if not history_data:
            return jsonify({'success': False, 'error': '加载历史对话数据失败'})
        
        # 从历史记录加载对话
        result = history_manager.load_conversation_from_history(history_data)
        
        if result["success"]:
            # 更新应用配置
            for key, value in result["app_config"].items():
                if key in app_state:
                    app_state[key] = value
            
            # 保存引擎状态以便后续初始化
            app_state["engine_state_to_load"] = result["engine_state"]
            
            # 更新应用状态
            app_state["app_stage"] = "initializing_narrative"
            
            # 更新小说信息
            if "metadata" in history_data:
                app_state["novel_title"] = history_data["metadata"].get("novel_name", "未知小说")
            
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result["error"]})
    except Exception as e:
        return jsonify({'success': False, 'error': f'加载历史对话出错: {str(e)}'})

@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    # 重置API配置
    default_config = config_manager.reset_api_config(DATA_DIR)
    
    # 更新应用状态
    for key, value in default_config.items():
        if key in app_state:
            app_state[key] = value
    
    return jsonify({'success': True})

@app.route('/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    
    # 更新UI设置
    if "show_typing_animation" in data:
        app_state["show_typing_animation"] = data["show_typing_animation"]
    
    if "typing_speed" in data:
        app_state["typing_speed"] = data["typing_speed"]
    
    if "enable_keyboard_shortcuts" in data:
        app_state["enable_keyboard_shortcuts"] = data["enable_keyboard_shortcuts"]
    
    # 更新模型参数
    updates = {}
    
    if "temperature" in data:
        app_state["temperature"] = data["temperature"]
        updates["temperature"] = data["temperature"]
    
    if "top_p" in data:
        app_state["top_p"] = data["top_p"]
        updates["top_p"] = data["top_p"]
    
    if "max_tokens" in data:
        app_state["max_tokens"] = data["max_tokens"]
        updates["max_tokens"] = data["max_tokens"]
    
    if "frequency_penalty" in data:
        app_state["frequency_penalty"] = data["frequency_penalty"]
        updates["frequency_penalty"] = data["frequency_penalty"]
    
    if "presence_penalty" in data:
        app_state["presence_penalty"] = data["presence_penalty"]
        updates["presence_penalty"] = data["presence_penalty"]
    
    # 更新叙事窗口设置
    if "initial_context_chapters" in data:
        app_state["initial_context_chapters"] = data["initial_context_chapters"]
        updates["initial_context_chapters"] = data["initial_context_chapters"]
    
    if "window_before" in data:
        app_state["window_before"] = data["window_before"]
        app_state["narrative_window_chapter_before"] = data["window_before"]  # 兼容前端
        updates["window_before"] = data["window_before"]
    
    if "window_after" in data:
        app_state["window_after"] = data["window_after"]
        app_state["narrative_window_chapter_after"] = data["window_after"]  # 兼容前端
        updates["window_after"] = data["window_after"]
    
    if "divergence_threshold" in data:
        app_state["divergence_threshold"] = data["divergence_threshold"]
        updates["divergence_threshold"] = data["divergence_threshold"]
    
    # 更新配置
    if updates:
        config_manager.update_api_config(DATA_DIR, updates)
    
    return jsonify({'success': True})

@app.route('/reset_journey', methods=['POST'])
def reset_journey():
    # 重置应用状态
    reset_for_new_journey()
    
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
