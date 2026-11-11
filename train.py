"""
Uruchom: python train.py --user mateusz
"""

import json
import sys
import argparse
import numpy as np
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
import joblib

from authtrace.config import DATA_DIR, MODELS_DIR
from authtrace.profiles import ProfileStore

# Zamiana features JSON -> wektor liczb dla ML
def features_to_vector(f: dict) -> list:
    #waga 3.0
    wpm              = f["typing_speed"]["wpm"]          * 3.0
    iki_median       = f["iki"]["median"]                * 3.0
    flight_median    = f["flight_time"]["median"]        * 3.0

    #waga 2.0
    dwell_mean       = f["dwell_time"]["mean"]           * 2.0
    dwell_std        = f["dwell_time"]["std"]            * 2.0
    iki_std          = f["iki"]["std"]                   * 2.0
    flight_std       = f["flight_time"]["std"]           * 2.0

    #waga 1.0
    dwell_median     = f["dwell_time"]["median"]         * 1.0
    iki_mean         = f["iki"]["mean"]                  * 1.0
    cps              = f["typing_speed"]["cps"]          * 1.0
    error_rate       = f["error_rate"]                   * 1.0
    avg_burst_len    = f["avg_burst_len"]                * 1.0
    shift_ratio      = f["shift_ratio"]                  * 1.0
    flight_mean      = f["flight_time"]["mean"]          * 1.0

    return [
        wpm, iki_median, flight_median,       # kluczowe
        dwell_mean, dwell_std,                # ważne
        iki_std, flight_std,                  # ważne
        dwell_median, iki_mean, cps,          # uzupełniające
        error_rate, avg_burst_len,            # uzupełniające
        shift_ratio, flight_mean,             # uzupełniające
    ]

#ladowanie wszystkich sesji użytkownika
def load_sessions(user: str) -> np.ndarray:
    data_dir = DATA_DIR / user
    vectors = []

    # sortowanie numeryczne (1, 2, ..., 10), a nie alfabetyczne (1, 10, 2)
    session_files = [data_dir / f"features_session_{i}.json" for i in ProfileStore().session_ids(user)]

    if not session_files:
        print(f"❌ Brak plików sesji w {data_dir}")
        sys.exit(1)

    for path in session_files:
        with open(path, encoding="utf-8") as f:
            features = json.load(f)
        vec = features_to_vector(features)
        vectors.append(vec)
        print(f"   ✅ Załadowano: {path.name}")

    return np.array(vectors)

#trening
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="default", help="Nazwa użytkownika")
    args = parser.parse_args()

    print(f"\n🧠 Trening modelu dla: {args.user}")
    print("─" * 40)

    X = load_sessions(args.user)
    print(f"\n📊 Załadowano {len(X)} sesji, {X.shape[1]} cech każda")

    #normalizacja — każda cecha przeskalowana do podobnego zakresu
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # One-Class SVM — uczy się jak TY piszesz
    # nu = ile % sesji może być "anomalią" (0.1 = 10% tolerancji)
    model = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")
    model.fit(X_scaled)

    # Sprawdź jak model ocenia Twoje własne sesje
    scores = model.decision_function(X_scaled)
    predictions = model.predict(X_scaled)
    correct = np.sum(predictions == 1)

    print(f"\n📈 Wyniki na danych treningowych:")
    print(f"   Sesji rozpoznanych jako TY: {correct}/{len(X)}")
    print(f"   Score min: {scores.min():.4f}")
    print(f"   Score max: {scores.max():.4f}")
    print(f"   Score avg: {scores.mean():.4f}")

    if correct < len(X) * 0.7:
        print("\n⚠️  Model rozpoznaje mniej niż 70% Twoich sesji.")
        print("   Zbierz więcej sesji lub zmień nu na 0.2")

    # Zapis modelu i skalera
    model_dir = MODELS_DIR / args.user
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model,  model_dir / "model.pkl")
    joblib.dump(scaler, model_dir / "scaler.pkl")

    print(f"\n✅ Model zapisany w: {model_dir}/")
    print(f"   Teraz uruchom: python verify.py --user {args.user}")

if __name__ == "__main__":
    main()