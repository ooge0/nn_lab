import plotly.express as px
import pandas as pd
import numpy as np
import os

# 1. ПІДГОТОВКА ДАНИХ
try:
    df = pd.read_json('./results/lab_export_20260508_185042.jsonl', lines=True)
    # df = pd.read_json('./results/lab_export.jsonl', lines=True)
except:
    models = ["llama3:latest", "qwen:latest", "phi3:latest"]
    df = pd.DataFrame([{
        "psychotype": np.random.choice(["Baseline","Hysteroid", "Schizoid", "Paranoid", "Epileptoid"]),
        "teacher": np.random.choice(models),
        "student": np.random.choice(models),
        "ms_per_word": np.random.uniform(100, 500),
        "lexical_density": np.random.uniform(0.3, 0.7),
        "cognitive_load": np.random.uniform(2, 12),
        "v_ok_numeric": np.random.choice([0, 1])
    } for _ in range(300)])

# Підготовка допоміжних колонок
df['psychotype_id'] = df['psychotype'].astype('category').cat.codes


def create_final_dashboard(df):
    # FIG 0: Потік логіки (Колір: Психотип)
    fig0 = px.parallel_categories(
        df, dimensions=['teacher', 'student', 'psychotype', 'v_ok_numeric'],
        color="psychotype_id",
        color_continuous_scale=px.colors.qualitative.Plotly,
        title="Logic Pipeline | Потік логіки (Колір: Психотип)"
    )
    fig0.update_layout(coloraxis_showscale=False)

    # FIG 1: Потік логіки (Колір: Результат)
    fig1 = px.parallel_categories(
        df, dimensions=['teacher', 'student', 'psychotype', 'v_ok_numeric'],
        color="v_ok_numeric", color_continuous_scale="RdYlGn",
        title="Logic Pipeline | Потік логіки (Колір: v_ok)"
    )

    # FIG 2: Ефективність пар
    fig2 = px.bar(
        df, x="student", y="ms_per_word", color="v_ok_numeric",
        facet_col="teacher", barmode="group",
        title="Productivity by Pair | Ефективність моделей"
    )

    # FIG 3: 3D Взаємодія
    fig3 = px.scatter_3d(
        df, x='lexical_density', y='ms_per_word', z='cognitive_load',
        color='psychotype', symbol='student',
        title="3D Interaction | 3D Взаємодія"
    )

    # FIG 4: Матриця вчителя
    fig4 = px.scatter_matrix(
        df, dimensions=['lexical_density', 'ms_per_word', 'cognitive_load'],
        color="teacher", title="Teacher Impact Matrix | Матриця впливу вчителя"
    )

    # FIG 5: Матриця вчитель + студент
    fig5 = px.scatter_matrix(
        df, dimensions=['lexical_density', 'ms_per_word', 'cognitive_load'],
        color="teacher", symbol="student",
        title="Cross-Model Dependency | Матриця залежностей: Вчитель та Студент"
    )
    fig5.update_traces(diagonal_visible=False, marker=dict(size=4))

    return [fig0, fig1, fig2, fig3, fig4, fig5]


if __name__ == "__main__":
    all_figs = create_final_dashboard(df)

    # Створюємо папку для окремих файлів, якщо її немає
    output_dir = "individual_plots"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # --- 1. ЗБЕРЕЖЕННЯ ЗАГАЛЬНОГО ЗВІТУ ---
    main_report = "full_lab_report.html"
    with open(main_report, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><head><meta charset='utf-8'>")
        f.write("<title>LLM Full Lab Report</title></head>")
        f.write("<body style='background-color:#0f0f0f; color:#fff; font-family:sans-serif; margin:0; padding:20px;'>")
        f.write("<h1 style='text-align:center;'>Аналіз N-вимірних даних LLM (Full Dashboard)</h1>")

        for i, fig in enumerate(all_figs):
            fig.update_layout(template="plotly_dark", height=750)

            # Додаємо в загальний звіт
            f.write(fig.to_html(full_html=False, include_plotlyjs='cdn' if i == 0 else False))
            f.write(
                "<div style='height:80px;'></div><hr style='border:1px solid #333;'><div style='height:40px;'></div>")

            # --- 2. ЗБЕРЕЖЕННЯ ОКРЕМИХ HTML ФАЙЛІВ ---
            # Очищуємо назву файлу від пробілів та спецсимволів
            clean_title = fig.layout.title.text.split('|')[0].strip().replace(' ', '_').lower()
            plot_name = f"plot_{i}_{clean_title}.html"
            plot_path = os.path.join(output_dir, plot_name)

            # Видалено параметр encoding, він не підтримується в методі write_html
            fig.write_html(plot_path, include_plotlyjs='cdn', full_html=True)
            print(f"Saved: {plot_path}")

        f.write("</body></html>")

    print(f"\n[DONE] Загальний звіт: {main_report}")
    print(f"[DONE] Окремі графіки збережено в папку: {output_dir}")
