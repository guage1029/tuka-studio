"""Legacy entry point; never load historical credentials or call a model on import."""

if __name__ == '__main__':
    print('原生 Gemini 接口已移除。请在 /app 选择国产厂商、填入 Key、刷新列表并选择模型。')
    print('离线测试：python -m unittest discover -s tests -v；真实测试须使用专用测试 Key。')
