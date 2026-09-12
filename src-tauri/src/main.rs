#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{process::{Command,Child},sync::Mutex};
use tauri::Manager;
struct Backend(Mutex<Option<Child>>);
#[tauri::command] fn get_branding() -> serde_json::Value { serde_json::json!({"product_name":"Otacon","tagline":"Local AI Command System","creator":"Antonio Garcia","show_creator_credit":true}) }
fn main(){ tauri::Builder::default().manage(Backend(Mutex::new(None))).setup(|app|{ let resource=app.path().resource_dir().unwrap().join("otacon-backend"); if resource.exists(){ let child=Command::new(resource).env("OTACON_PORT","8787").spawn().ok(); *app.state::<Backend>().0.lock().unwrap()=child; } if let Some(w)=app.get_webview_window("main"){ let _=w.eval("window.location.href='http://127.0.0.1:8787/'"); } Ok(()) }).invoke_handler(tauri::generate_handler![get_branding]).run(tauri::generate_context!()).expect("error while running Otacon"); }
