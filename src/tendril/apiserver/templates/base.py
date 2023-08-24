

from inspect import signature
from makefun import create_function


class ApiRouterGenerator(object):
    def _inject_model(self, ep, param, model):
        orig_sig = signature(ep)
        params = list(orig_sig.parameters.values())
        orig_param = next(p for p in params if p.name == param)
        index = params.index(orig_param)
        new_param = orig_param.replace(name=orig_param.name,
                                       default=orig_param.default,
                                       kind=orig_param.kind,
                                       annotation=model)
        params[index] = new_param
        new_sig = orig_sig.replace(parameters=params)
        return create_function(func_signature=new_sig, func_impl=ep)

    async def placeholder(self):
        pass

    def generate(self, prefix):
        raise NotImplementedError
