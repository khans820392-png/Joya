कैसे चलाएँ (लैपटॉप पर)
1) pip install -r requirements.txt
2) टर्मिनल 1:  python server.py        -> ब्राउज़र में http://localhost:5000
3) टर्मिनल 2:  python print_agent.py   -> पेमेंट के बाद यहाँ "[प्रिंट] ..." दिखेगा
फोन से टेस्ट: लैपटॉप और फोन एक ही वाईफाई पर हों, फोन में http://<लैपटॉप-का-IP>:5000 खोलें।
असली प्रिंट: print_agent.py में MODE = "print" करें (Windows)।