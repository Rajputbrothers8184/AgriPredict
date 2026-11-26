# User guide

For the person using AgriPredict in a mandi, not for the person deploying it.
Written to be followed on a phone with one hand.

The app is bilingual — **English / اردو**. The language switch is on the sign-in
screen and in Settings; it applies immediately to labels and right-to-left
layout on the next launch (React Native cannot flip direction in a running
session).

---

## 1. First run

1. Open the app. You see the **sign-in** screen.
2. If you have no account, tap **Create account**.
3. Enter your email, a password of at least 8 characters containing a letter and
   a digit, and your name.
4. You land on the **Home** screen with an empty dashboard. That is correct — the
   app does not invent data.

You can change the language from the sign-in screen before you even have an
account.

---

## 2. The order things must be done in

The app deliberately enforces this order, because a sale with no crop behind it
cannot be costed:

```
Farm  →  Crop cycle  →  Expenses + Sales  →  Finance summary  →  Reports
```

If you try to skip a step the app explains what is missing rather than accepting
half a record.

### Step 1 — Add your farm

**Home → Farms → + Add farm**

| Field | Notes |
| --- | --- |
| Name | Anything you recognise: "Haveli field", "Canal side" |
| District | Used for weather and buyer search |
| Location | Optional. Tap **Use my location**, or enter both coordinates |
| Total area | In acres. You can split it into several crop cycles |

One coordinate without the other is rejected — half a location is worse than
none, because weather would be requested for the wrong place.

### Step 2 — Start a crop cycle

**Farms → your farm → + New crop cycle**

| Field | Notes |
| --- | --- |
| Commodity | Wheat, rice, cotton, maize, potato, onion… 16 are available |
| Season | Kharif or Rabi; the app guesses from the sowing date |
| Area | Acres used by **this** crop on this farm |
| Sowing date | Cannot be after the harvest date |

The app then shows the expected harvest date and an expected yield based on the
area.

### Step 3 — Record expenses and sales as they happen

**Crop cycle → Expenses → +**

Four categories: **Seeds, Fertiliser, Pesticide, Labour**. Each needs an amount
and a date. Record them when they happen — the value of the app is in the
running total, not in a reconstruction at the end of the season.

**Crop cycle → Sales → +**

| Field | Notes |
| --- | --- |
| Quantity | In **kilograms** — the weight you actually weighed out |
| Price | In **PKR per maund (40 kg)** — the way the mandi quotes |

The app multiplies them for you and shows the total before you save. You do not
type the total; that is deliberate, because it is the step where a
kilogram/maund mistake turns into a 40× error in your profit.

> **The 40 kg rule.** Every price in this app is per maund, and one maund is
> 40 kg. 400 kg sold at PKR 4,000/maund is PKR 40,000, not PKR 1,600,000. The
> price is always shown with its unit attached so the two cannot be confused.

### Step 4 — Read your numbers

**Crop cycle → Summary**

| Shown | Means |
| --- | --- |
| Revenue | Everything you have sold so far from this cycle |
| Cost | Every expense recorded against it |
| Profit | Revenue − cost. Negative is shown in red, not hidden |
| Margin | Profit as a percentage of revenue |
| Break-even price | The price per maund at which you stop losing money on this crop |
| Yield per acre | Harvested kilograms ÷ acres |

**Break-even price** is the number to take to the mandi. If your break-even is
PKR 2,000/maund and the market is at 2,400, selling is profitable; at 1,800 it is
not. It is recalculated from your real expenses, not from an average.

---

## 3. Prices and forecasts

**Prices** tab:

* Pick a **commodity** and a **market** to see the price history.
* Prices are quoted per **40 kg maund**, and the chart says so.
* **Compare markets** shows the same commodity across several mandis and names
  the best one — that difference is often the whole margin.

**Forecast**:

* Choose a horizon of **7 or 30 days**.
* You get a line with an upper and lower bound. The band is honest: a wide band
  means the model is unsure, and a model that could not beat a "same day last
  week" baseline is never presented as if it could.
* The screen shows **which model produced this forecast** and its measured
  average error (MAE). If it says the error is PKR 103, treat a
  PKR 50 difference between two mandis as noise.

> **Read this before acting on a forecast.** The price history in this build is
> marked **`synthetic_fixture`** — simulated data used to exercise the pipeline.
> The app shows a warning banner whenever that is the source. The forecasts are
> therefore a demonstration of the method, not a prediction of the Pakistani
> market. Do not make a selling decision on them until real AMIS Punjab / PBS
> data is loaded.

---

## 4. Weather

**Weather** shows current conditions and a short forecast for your farm's
district.

If the card says **simulated**, no live provider key is configured and the values
are not real. The app will not present invented weather as observation.

---

## 5. Buyers

**Buyers** finds nearby traders, commission agents and cold storage.

It needs a location and a Google Places key configured on the server. If the key
is missing, the screen says the search is **unavailable** and stays empty. That
is a configuration gap, not a bug — and an empty list is better than a list of
businesses that may not exist.

Tapping a buyer's number opens your dialler.

---

## 6. Reports

**Reports → choose PDF or Excel → Generate**

| Format | Use it for |
| --- | --- |
| PDF | Printing, or showing a lender or buyer a clean summary |
| Excel (.xlsx) | Your own records, or a cooperative's books |

The file opens in your phone's browser or download manager. The download link is
valid for **5 minutes**; if it expires, generate the report again. Nothing is
charged and nothing is shared — the file is generated on your own account and
only you can download it.

---

## 7. Your data and your account

* **Only you can see your data.** Another account cannot read, change or delete
  your farm, cycles, expenses or reports — the server refuses, and does not even
  confirm that your record exists.
* **Always sign out on a shared phone.** **More → Sign out** removes the stored
  tokens from that device.
* **If you lose your phone or think someone knows your password**, use
  **More → Sign out on all devices**. It asks you to confirm, then ends every
  session for the account immediately — including any phone that is still signed
  in somewhere else. Ordinary sign-out only ends the session on the device you
  are holding.
* **Changing your password signs you out everywhere.** This is deliberate.
* **Forgot your password?** There is no self-service reset in this build. A farm
  record is not recoverable without the account, so contact whoever runs your
  deployment.

---

## 8. When something looks wrong

| What you see | What it means | What to do |
| --- | --- | --- |
| "Network request failed" | The phone cannot reach the server | Check Wi-Fi/data; the server address is set when the app is built |
| A price shows `—` | No quote exists for that day | Try another market or a wider range |
| Forecast says `seasonal_naive` | The trained model was unavailable | The forecast is a simple baseline; treat it as such |
| Weather says "simulated" | No weather provider key configured | Ask your administrator |
| Buyers is empty | No Places key configured | Ask your administrator |
| "Too many requests" | Sign-in is rate-limited (correct behaviour) | Wait a minute and try again |
| Banner: "synthetic_fixture" | The prices are simulated demonstration data | Do not make selling decisions on them |

---

## 9. Tips that matter more than the app

1. **Record the expense the day you pay it.** A season reconstructed from memory
   is always more profitable than the real one, which defeats the purpose.
2. **Weigh in kilograms, price in maunds.** The app converts; you only need to
   be sure which number is which.
3. **Check two mandis before selling.** The comparison screen exists because the
   spread is often larger than the cost of transport.
4. **Use break-even, not hope.** It is the one number that tells you whether
   waiting is a decision or a gamble.
