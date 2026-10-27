"""One shared model-call budget across a chat turn and nested PLC workflow."""
from .provider import ProviderError


class CallBudgetExceeded(ProviderError):
    pass


class CallBudget:
    def __init__(self,provider,limit):
        self.provider=provider;self.limit=limit;self.calls=0

    @property
    def cancel_event(self):return self.provider.cancel_event

    def reset(self):self.calls=0

    def cancel(self):self.provider.cancel()

    def complete(self,*args,**kwargs):
        if self.calls>=self.limit:
            raise CallBudgetExceeded('已达到本轮模型调用预算，包含摘要和PLC流程内部请求；已有文件与证据保留。')
        self.calls+=1
        provider=kwargs.pop('_provider_override',self.provider)
        return provider.complete(*args,**kwargs)
