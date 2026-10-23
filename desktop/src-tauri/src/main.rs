// En Windows no abre una consola junto a la ventana.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    jobhunter_desktop_lib::run()
}
