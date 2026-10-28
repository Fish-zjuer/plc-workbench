"""Strict ST frontend for symbolic scan transitions. Unknown syntax is never skipped."""
from __future__ import annotations
from dataclasses import dataclass
import re

INTEGER_TYPES={"SINT":(8,True),"USINT":(8,False),"BYTE":(8,False),
               "INT":(16,True),"UINT":(16,False),"WORD":(16,False),
               "DINT":(32,True),"UDINT":(32,False),"DWORD":(32,False)}
SUPPORTED={"BOOL",*INTEGER_TYPES}

class UnsupportedST(ValueError):pass

def tokens(source):
    # Preserve positions and handle nested comments instead of regex-deleting program fragments.
    out=[];i=0
    pattern=re.compile(r":=|<=|>=|<>|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[():;,=<>+\-*/]")
    while i<len(source):
        if source[i].isspace():i+=1;continue
        if source.startswith("//",i):
            end=source.find("\n",i);i=len(source) if end<0 else end;continue
        if source.startswith("(*",i):
            depth=1;i+=2
            while i<len(source) and depth:
                if source.startswith("(*",i):depth+=1;i+=2
                elif source.startswith("*)",i):depth-=1;i+=2
                else:i+=1
            if depth:raise UnsupportedST("Unclosed ST comment")
            continue
        match=pattern.match(source,i)
        if not match:raise UnsupportedST(f"Unsupported token at line {source.count(chr(10),0,i)+1}: {source[i:i+30]}")
        out.append(match[0].upper());i=match.end()
    if len(out)>6000:raise UnsupportedST("Formal frontend token budget exceeded")
    return out+["<EOF>"]

class Parser:
    PRECEDENCE={"OR":1,"XOR":2,"AND":3,"=":4,"<>":4,"<":4,"<=":4,">":4,">=":4,"+":5,"-":5,"*":6,"/":6,"MOD":6}
    def __init__(self,source):
        self.stream=tokens(source);self.pos=0;self.declarations={};self.directions={};self.initializers={}
    def take(self,expected=None):
        value=self.stream[self.pos]
        if expected is not None and value!=expected:raise UnsupportedST(f"Expected {expected}, got {value}")
        self.pos+=1;return value
    def peek(self):return self.stream[self.pos]
    def name(self):
        value=self.take()
        if not re.fullmatch(r"[A-Z_][A-Z_0-9]*",value):raise UnsupportedST("Expected identifier")
        return value
    def expr(self,minimum=0,depth=0):
        if depth>64:raise UnsupportedST("Expression nesting budget exceeded")
        token=self.take()
        if token=="(":
            left=self.expr(depth=depth+1);self.take(")")
        elif token in ("NOT","-","+"):left=("unary",token,self.expr(7,depth+1))
        elif token in ("TRUE","FALSE"):left=("literal",token=="TRUE")
        elif token.isdigit():left=("literal",int(token))
        elif re.fullmatch(r"[A-Z_][A-Z_0-9]*",token):left=("var",token)
        else:raise UnsupportedST("Unsupported expression token: "+token)
        while self.peek() in self.PRECEDENCE and self.PRECEDENCE[self.peek()]>=minimum:
            op=self.take();right=self.expr(self.PRECEDENCE[op]+1,depth+1);left=("binary",op,left,right)
        return left
    def statements(self,stops,depth=0):
        if depth>32:raise UnsupportedST("Statement nesting budget exceeded")
        result=[]
        while self.peek() not in stops:
            token=self.peek()
            if token==";":self.take();continue
            if token=="IF":
                branches=[];self.take()
                condition=self.expr();self.take("THEN")
                branches.append((condition,self.statements({"ELSIF","ELSE","END_IF"},depth+1)))
                while self.peek()=="ELSIF":
                    self.take();condition=self.expr();self.take("THEN")
                    branches.append((condition,self.statements({"ELSIF","ELSE","END_IF"},depth+1)))
                otherwise=[]
                if self.peek()=="ELSE":self.take();otherwise=self.statements({"END_IF"},depth+1)
                self.take("END_IF")
                if self.peek()==";":self.take()
                result.append(("if",branches,otherwise))
            else:
                name=self.name();self.take(":=");expression=self.expr();self.take(";")
                if name not in self.declarations or self.directions[name]=="inputs":
                    raise UnsupportedST("Assignment to unknown/read-only input: "+name)
                result.append(("assign",name,expression))
        return result
    def parse(self):
        self.take("FUNCTION_BLOCK");name=self.name()
        while self.peek() in ("VAR_INPUT","VAR_OUTPUT","VAR"):
            kind=self.take();direction={"VAR_INPUT":"inputs","VAR_OUTPUT":"outputs","VAR":"locals"}[kind]
            while self.peek()!="END_VAR":
                names=[self.name()]
                while self.peek()==",":self.take();names.append(self.name())
                self.take(":");dtype=self.take()
                if dtype not in SUPPORTED:raise UnsupportedST("Formal type not supported: "+dtype)
                initializer=("literal",False if dtype=="BOOL" else 0)
                if self.peek()==":=":self.take();initializer=self.expr()
                self.take(";")
                for variable in names:
                    if variable in self.declarations:raise UnsupportedST("Duplicate declaration: "+variable)
                    self.declarations[variable]=dtype;self.directions[variable]=direction
                    self.initializers[variable]=initializer
            self.take("END_VAR")
        body=self.statements({"END_FUNCTION_BLOCK"})
        self.take("END_FUNCTION_BLOCK")
        if self.peek()==";":self.take()
        self.take("<EOF>")
        if len(self.declarations)>128:raise UnsupportedST("State variable budget exceeded")
        return Program(name,self.declarations,self.directions,self.initializers,body)

@dataclass
class Value:
    term: object
    dtype: str

@dataclass
class Program:
    name: str
    types: dict
    directions: dict
    initializers: dict
    body: list

    def value(self,value,dtype,z3):
        if dtype=="BOOL":
            if type(value) is not bool:raise UnsupportedST("BOOL/integer coercion is not modeled")
            return Value(z3.BoolVal(value),dtype)
        if type(value) is not int:raise UnsupportedST("Integer value expected")
        width,signed=INTEGER_TYPES[dtype]
        lo=-(2**(width-1)) if signed else 0;hi=2**(width-1)-1 if signed else 2**width-1
        if not lo<=value<=hi:raise UnsupportedST("Out-of-range literal for "+dtype)
        return Value(z3.BitVecVal(value,width),dtype)

    def variable(self,name,dtype,z3):
        return Value(z3.Bool(name) if dtype=="BOOL" else z3.BitVec(name,INTEGER_TYPES[dtype][0]),dtype)

    def expression(self,node,env,z3):
        kind=node[0]
        if kind=="literal":return Value(z3.BoolVal(node[1]),"BOOL") if type(node[1]) is bool else Value(node[1],"literal")
        if kind=="var":
            if node[1] not in env:raise UnsupportedST("Undeclared expression variable: "+node[1])
            return env[node[1]]
        if kind=="unary":
            op=node[1];v=self.expression(node[2],env,z3)
            if op=="NOT":
                if v.dtype=="BOOL":return Value(z3.Not(v.term),"BOOL")
                if v.dtype in ("BYTE","WORD","DWORD"):return Value(~v.term,v.dtype)
                raise UnsupportedST("NOT type not modeled")
            if op in ("+","-") and v.dtype!="BOOL":
                return Value(v.term if op=="+" else -v.term,v.dtype)
            raise UnsupportedST("Invalid unary operand")
        op=node[1];left=self.expression(node[2],env,z3);right=self.expression(node[3],env,z3)
        if left.dtype=="literal" and right.dtype!="literal":left=self.value(left.term,right.dtype,z3)
        if right.dtype=="literal" and left.dtype!="literal":right=self.value(right.term,left.dtype,z3)
        if left.dtype!=right.dtype:raise UnsupportedST("Mixed type promotions require target-specific semantics")
        if op in ("=","<>","<","<=",">",">="):
            # Intermediate integer expression width varies by target; refuse to guess.
            if has_arithmetic(node[2]) or has_arithmetic(node[3]):raise UnsupportedST("Arithmetic inside comparison is target-width dependent")
            if op in ("=","<>"):term=left.term==right.term if op=="=" else left.term!=right.term
            else:
                if left.dtype=="BOOL":raise UnsupportedST("BOOL ordering is unsupported")
                if left.dtype in INTEGER_TYPES and not INTEGER_TYPES[left.dtype][1]:
                    term={"<":z3.ULT,"<=":z3.ULE,">":z3.UGT,">=":z3.UGE}[op](left.term,right.term)
                else:term={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b}[op](left.term,right.term)
            return Value(z3.BoolVal(term) if type(term) is bool else term,"BOOL")
        if op in ("AND","OR","XOR"):
            if left.dtype=="BOOL":
                return Value({"AND":z3.And,"OR":z3.Or,"XOR":z3.Xor}[op](left.term,right.term),"BOOL")
            if left.dtype not in ("BYTE","WORD","DWORD"):raise UnsupportedST("Integer logical operator type not modeled")
            return Value({"AND":lambda a,b:a&b,"OR":lambda a,b:a|b,"XOR":lambda a,b:a^b}[op](left.term,right.term),left.dtype)
        if op in ("+","-") and left.dtype!="BOOL":
            return Value(left.term+right.term if op=="+" else left.term-right.term,left.dtype)
        raise UnsupportedST("Operator not in formal subset: "+op)

    def execute(self,env,z3,statements=None):
        out=dict(env)
        for statement in self.body if statements is None else statements:
            if statement[0]=="assign":
                _,name,node=statement;value=self.expression(node,out,z3);dtype=self.types[name]
                if value.dtype=="literal":value=self.value(value.term,dtype,z3)
                if value.dtype!=dtype:raise UnsupportedST("Implicit assignment conversion is not modeled")
                out[name]=value
            else:
                _,branches,otherwise=statement
                merged=self.execute(out,z3,otherwise)
                for condition,body in reversed(branches):
                    test=self.expression(condition,out,z3)
                    if test.dtype!="BOOL":raise UnsupportedST("IF condition must be BOOL")
                    changed=self.execute(out,z3,body)
                    merged={n:Value(z3.If(test.term,changed[n].term,merged[n].term),out[n].dtype) for n in out}
                out=merged
        return out

    def initial_state(self,z3):
        env={}
        for name,dtype in self.types.items():
            if self.directions[name]=="inputs":continue
            node=self.initializers[name]
            value=self.expression(node,{},z3)
            if value.dtype=="literal":value=self.value(value.term,dtype,z3)
            if value.dtype!=dtype:raise UnsupportedST("Initial value type mismatch")
            env[name]=value
        return env

def has_arithmetic(node):
    if node[0]=='literal':return False
    if node[0]=='var':return False
    if node[0]=="binary":return (node[1] in ("+","-","*","/","MOD") and contains_variable(node)) or has_arithmetic(node[2]) or has_arithmetic(node[3])
    if node[0]=="unary":return (node[1] in ("+","-") and contains_variable(node)) or has_arithmetic(node[2])
    return False

def contains_variable(node):
    if node[0]=='var':return True
    if node[0]=='unary':return contains_variable(node[2])
    if node[0]=='binary':return contains_variable(node[2]) or contains_variable(node[3])
    return False

def parse(source):return Parser(source).parse()
