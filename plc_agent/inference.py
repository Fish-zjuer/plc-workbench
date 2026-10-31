"""Explicit per-model inference controls for Chat Completions experiments."""
from dataclasses import replace
from .config import ModelConfig

CONTROL_KEYS={'thinking','reasoning_effort','enable_thinking','thinking_budget','reasoning'}

def inference_config(cfg, model, settings=None):
    settings={} if settings is None else settings
    if not isinstance(settings,dict) or settings.keys()-{'mode','budget','parameters'}:
        raise ValueError('推理设置字段无效')
    mode=settings.get('mode','default')
    if mode not in ('default','off','on','low','high','max','custom'):
        raise ValueError('未知推理模式')
    budget=settings.get('budget')
    if budget is not None and (type(budget) is not int or budget<1):
        raise ValueError('思考预算必须为正整数')
    params=settings.get('parameters',{})
    if not isinstance(params,dict):raise ValueError('高级参数必须为 JSON 对象')
    if mode!='custom' and params:raise ValueError('仅高级模式可填写自定义参数')
    extra=dict(cfg.extra_body)
    if mode!='default':
        for key in CONTROL_KEYS:extra.pop(key,None)
    name=model.lower()
    if mode=='custom':
        # Reuse transport validation, never permit model/key/message overrides.
        replace(cfg,extra_body=params).validate(require_ready=False)
        extra.update(params)
    elif mode!='default':
        if name.startswith('deepseek'):
            if mode in ('low','high','max') and not ('v4' in name or name=='deepseek-flash'):
                raise ValueError('此 DeepSeek 型号未配置推理档位，请使用开关或高级参数')
            extra['thinking']={'type':'disabled' if mode=='off' else 'enabled'}
            if mode in ('low','high','max'):extra['reasoning_effort']=mode
            if budget is not None:raise ValueError('DeepSeek 不使用 Qwen 思考预算字段')
        elif name.startswith('qwen3') and not any(x in name for x in ('image','omni')):
            if mode not in ('off','on'):raise ValueError('Qwen 请选择思考开关及可选预算')
            extra['enable_thinking']=mode=='on'
            if budget is not None:
                if mode!='on':raise ValueError('仅开启思考时可设置预算')
                if budget>=cfg.max_output_tokens:raise ValueError('思考预算必须小于最大输出 Token 数')
                extra['thinking_budget']=budget
        else:raise ValueError('此模型请使用服务默认或按中转站文档填写高级参数')
    elif budget is not None:raise ValueError('服务默认模式不接受思考预算')
    result=replace(cfg,model=model,extra_body=extra)
    # Qwen thinking requires streaming. Both frameworks use the same setting.
    if extra.get('enable_thinking') is True:result=replace(result,stream=True)
    result.validate(require_ready=False)
    return result
