import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import { initializeFirestore, doc, setDoc, updateDoc, onSnapshot, increment }
  from "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyAzqJaXy5oWTiWaP7UcfMgNbCXQe7dYeIk",
  authDomain: "corpflow-fba92.firebaseapp.com",
  projectId: "corpflow-fba92",
  storageBucket: "corpflow-fba92.firebasestorage.app",
  messagingSenderId: "587228131224",
  appId: "1:587228131224:web:57780c8eecb4a3c5f685ed"
};

const app = initializeApp(firebaseConfig);
const db = initializeFirestore(app, { experimentalForceLongPolling: true });

export const ref = doc(db, "corpflow", "current");
export const EMPLOYEES = [
  { id: "rahul", name: "Rahul" },
  { id: "amit", name: "Amit" },
  { id: "aman", name: "Aman" }
];
export const inr = n => "\u20B9" + Number(n || 0).toLocaleString("en-IN");
export { setDoc, updateDoc, onSnapshot, increment };