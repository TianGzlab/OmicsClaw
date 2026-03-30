"""
Clinical Validation Functions for Disease Progression Trajectories

This module provides functions for validating disease progression trajectories
against clinical measures, outcomes, and staging systems.
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, mannwhitneyu, kruskal
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.statistics import logrank_test
from plotnine import (ggplot, aes, geom_boxplot, geom_step, labs,
                      theme_minimal, facet_wrap)
from plotnine_prism import theme_prism


def correlate_with_clinical_scores(metadata, pseudotime_column='pseudotime',
                                    clinical_columns=None):
    """
    Correlate pseudotime with clinical severity scores.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata with pseudotime and clinical scores
    pseudotime_column : str
        Column name for pseudotime values
    clinical_columns : list of str, optional
        Clinical score columns to correlate. If None, auto-detect numeric columns.

    Returns
    -------
    pd.DataFrame
        Correlation results with columns: variable, correlation, pvalue
    """
    if clinical_columns is None:
        # Auto-detect numeric columns (excluding pseudotime)
        clinical_columns = metadata.select_dtypes(include=[np.number]).columns
        clinical_columns = [c for c in clinical_columns
                            if c != pseudotime_column and c != 'patient_id']

    results = []

    for col in clinical_columns:
        # Remove missing values
        valid_mask = ~metadata[col].isnull() & ~metadata[pseudotime_column].isnull()
        if valid_mask.sum() < 3:
            continue  # Skip if too few valid pairs

        corr, pval = spearmanr(metadata.loc[valid_mask, pseudotime_column],
                               metadata.loc[valid_mask, col])

        results.append({
            'variable': col,
            'correlation': corr,
            'pvalue': pval,
            'n_samples': valid_mask.sum()
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('pvalue')

    # Print summary
    print("Pseudotime vs. Clinical Scores Correlation")
    print("=" * 60)
    for _, row in results_df.iterrows():
        print(f"{row['variable']:30s} r={row['correlation']:6.3f}  p={row['pvalue']:.3e}  n={row['n_samples']}")

    return results_df


def compare_by_clinical_stage(metadata, pseudotime_column='pseudotime',
                               stage_column='clinical_stage',
                               output_file=None):
    """
    Compare pseudotime across discrete clinical stages.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata with pseudotime and clinical stage
    pseudotime_column : str
        Column name for pseudotime values
    stage_column : str
        Column name for clinical stage categories
    output_file : str, optional
        If provided, save boxplot to this file

    Returns
    -------
    dict
        Statistical test results
    """
    # Remove missing values
    valid_mask = ~metadata[stage_column].isnull() & ~metadata[pseudotime_column].isnull()
    data_valid = metadata.loc[valid_mask].copy()

    # Kruskal-Wallis test (non-parametric ANOVA)
    stages = data_valid[stage_column].unique()
    stage_groups = [data_valid[data_valid[stage_column] == s][pseudotime_column].values
                    for s in stages]

    h_stat, kw_pval = kruskal(*stage_groups)

    print("\nPseudotime Comparison Across Clinical Stages")
    print("=" * 60)
    print(f"Kruskal-Wallis Test: H={h_stat:.2f}, p={kw_pval:.3e}")

    # Pairwise comparisons (Mann-Whitney U test)
    pairwise_results = []
    for i in range(len(stages)):
        for j in range(i + 1, len(stages)):
            group1 = data_valid[data_valid[stage_column] == stages[i]][pseudotime_column]
            group2 = data_valid[data_valid[stage_column] == stages[j]][pseudotime_column]

            u_stat, mw_pval = mannwhitneyu(group1, group2)

            pairwise_results.append({
                'stage1': stages[i],
                'stage2': stages[j],
                'u_statistic': u_stat,
                'pvalue': mw_pval,
                'median_diff': group2.median() - group1.median()
            })

            print(f"  {stages[i]} vs {stages[j]}: p={mw_pval:.3e}")

    # Visualization
    if output_file:
        plot = (ggplot(data_valid, aes(x=stage_column, y=pseudotime_column, fill=stage_column))
                + geom_boxplot(alpha=0.7)
                + labs(title='Pseudotime by Clinical Stage',
                       x='Clinical Stage',
                       y='Pseudotime')
                + theme_prism())

        plot.save(output_file, dpi=300, width=8, height=6)
        print(f"\nBoxplot saved to: {output_file}")

    return {
        'kruskal_wallis': {'h_statistic': h_stat, 'pvalue': kw_pval},
        'pairwise_comparisons': pd.DataFrame(pairwise_results)
    }


def survival_analysis(metadata, pseudotime_column='pseudotime',
                      time_column='time_to_event', event_column='event_occurred',
                      output_file=None):
    """
    Perform survival analysis using pseudotime as predictor.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata with pseudotime, survival time, and event status
    pseudotime_column : str
        Column name for pseudotime values
    time_column : str
        Column name for time to event (days, months, etc.)
    event_column : str
        Column name for event occurrence (1=event, 0=censored)
    output_file : str, optional
        If provided, save Kaplan-Meier plot to this file

    Returns
    -------
    dict
        Cox PH model results and log-rank test results
    """
    # Remove missing values
    required_cols = [pseudotime_column, time_column, event_column]
    valid_mask = ~metadata[required_cols].isnull().any(axis=1)
    data_valid = metadata.loc[valid_mask, required_cols].copy()

    if len(data_valid) < 10:
        raise ValueError("Insufficient samples for survival analysis (need ≥10)")

    # Cox proportional hazards model
    print("\nCox Proportional Hazards Model")
    print("=" * 60)

    cph = CoxPHFitter()
    cph.fit(data_valid, duration_col=time_column, event_col=event_column)

    print(cph.summary)

    # Hazard ratio
    hr = np.exp(cph.params_[pseudotime_column])
    hr_ci = np.exp(cph.confidence_intervals_.loc[pseudotime_column].values)

    print(f"\nHazard Ratio for {pseudotime_column}:")
    print(f"  HR = {hr:.3f} (95% CI: {hr_ci[0]:.3f}-{hr_ci[1]:.3f})")

    # Dichotomize by pseudotime median for Kaplan-Meier
    median_pseudotime = data_valid[pseudotime_column].median()
    data_valid['trajectory_group'] = data_valid[pseudotime_column] > median_pseudotime
    data_valid['trajectory_group_label'] = data_valid['trajectory_group'].map(
        {True: 'Advanced', False: 'Early'}
    )

    # Kaplan-Meier analysis
    print("\nKaplan-Meier Survival Analysis")
    print("=" * 60)

    kmf = KaplanMeierFitter()

    # Prepare data for plotting
    km_data = []

    for group_label in ['Early', 'Advanced']:
        group_mask = data_valid['trajectory_group_label'] == group_label
        group_data = data_valid[group_mask]

        kmf.fit(group_data[time_column],
                group_data[event_column],
                label=f"{group_label} progression")

        # Extract survival function for plotting
        sf = kmf.survival_function_.reset_index()
        sf.columns = ['time', 'survival']
        sf['group'] = group_label
        km_data.append(sf)

        # Print median survival
        median_survival = kmf.median_survival_time_
        print(f"  {group_label} progression: median survival = {median_survival:.1f}")

    # Log-rank test
    early = data_valid[data_valid['trajectory_group_label'] == 'Early']
    advanced = data_valid[data_valid['trajectory_group_label'] == 'Advanced']

    logrank_result = logrank_test(
        early[time_column], advanced[time_column],
        early[event_column], advanced[event_column]
    )

    print(f"\nLog-rank test: p={logrank_result.p_value:.3e}")

    # Visualization
    if output_file:
        km_plot_data = pd.concat(km_data)

        plot = (ggplot(km_plot_data, aes(x='time', y='survival', color='group'))
                + geom_step(size=1.5)
                + labs(title='Kaplan-Meier Survival Curves',
                       x='Time',
                       y='Survival Probability',
                       color='Trajectory Group')
                + theme_prism())

        plot.save(output_file, dpi=300, width=8, height=6)
        print(f"\nKaplan-Meier plot saved to: {output_file}")

    return {
        'cox_model': {
            'hazard_ratio': hr,
            'hr_ci_lower': hr_ci[0],
            'hr_ci_upper': hr_ci[1],
            'pvalue': cph.summary.loc[pseudotime_column, 'p']
        },
        'logrank_test': {
            'test_statistic': logrank_result.test_statistic,
            'pvalue': logrank_result.p_value
        },
        'median_survival': {
            'early': kmf.median_survival_time_
            # Note: would need to refit for 'advanced' group
        }
    }


def outcome_prediction(features, pseudotime, outcome, test_size=0.3,
                       random_state=42):
    """
    Build predictive model for clinical outcome using trajectory features.

    Parameters
    ----------
    features : pd.DataFrame
        Feature matrix (features × samples)
    pseudotime : array-like
        Pseudotime for each sample
    outcome : array-like
        Binary outcome variable (e.g., responder vs. non-responder)
    test_size : float
        Fraction of data to use for testing
    random_state : int
        Random seed for reproducibility

    Returns
    -------
    dict
        Model performance metrics and feature importance
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.metrics import roc_auc_score, classification_report

    # Prepare feature matrix (add pseudotime as feature)
    X = features.T.copy()
    X['pseudotime'] = pseudotime

    y = outcome.values if isinstance(outcome, pd.Series) else outcome

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    # Train Random Forest classifier
    clf = RandomForestClassifier(n_estimators=100, random_state=random_state,
                                  max_depth=10, min_samples_split=5)
    clf.fit(X_train, y_train)

    # Cross-validation on training set
    cv_scores = cross_val_score(clf, X_train, y_train, cv=5, scoring='roc_auc')

    # Test set performance
    y_pred_proba = clf.predict_proba(X_test)[:, 1]
    test_auc = roc_auc_score(y_test, y_pred_proba)

    y_pred = clf.predict(X_test)
    class_report = classification_report(y_test, y_pred, output_dict=True)

    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'importance': clf.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\nOutcome Prediction Model Performance")
    print("=" * 60)
    print(f"Cross-validated AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    print(f"Test AUC: {test_auc:.3f}")
    print("\nTop 10 Predictive Features:")
    print(feature_importance.head(10))

    return {
        'model': clf,
        'cv_auc_mean': cv_scores.mean(),
        'cv_auc_std': cv_scores.std(),
        'test_auc': test_auc,
        'classification_report': class_report,
        'feature_importance': feature_importance
    }


def compute_progression_rate(metadata, pseudotime_column='pseudotime',
                              time_column='timepoint', patient_column='patient_id'):
    """
    Calculate disease progression rate for each patient.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata with pseudotime, timepoint, and patient ID
    pseudotime_column : str
        Column name for pseudotime values
    time_column : str
        Column name for timepoint values
    patient_column : str
        Column name for patient identifier

    Returns
    -------
    pd.DataFrame
        Per-patient progression rates
    """
    from scipy.stats import linregress

    progression_rates = []

    for patient in metadata[patient_column].unique():
        patient_data = metadata[metadata[patient_column] == patient].copy()
        patient_data = patient_data.sort_values(time_column)

        if len(patient_data) < 2:
            continue  # Need at least 2 timepoints

        # Linear regression: pseudotime ~ timepoint
        slope, intercept, r_value, p_value, std_err = linregress(
            patient_data[time_column],
            patient_data[pseudotime_column]
        )

        progression_rates.append({
            'patient_id': patient,
            'n_timepoints': len(patient_data),
            'baseline_pseudotime': patient_data[pseudotime_column].iloc[0],
            'final_pseudotime': patient_data[pseudotime_column].iloc[-1],
            'time_range': patient_data[time_column].max() - patient_data[time_column].min(),
            'progression_rate': slope,
            'progression_r2': r_value ** 2,
            'progression_pvalue': p_value
        })

    progression_df = pd.DataFrame(progression_rates)

    print("\nDisease Progression Rates Per Patient")
    print("=" * 60)
    print(f"Mean progression rate: {progression_df['progression_rate'].mean():.4f} ± "
          f"{progression_df['progression_rate'].std():.4f}")
    print(f"Fastest progressor: {progression_df['progression_rate'].max():.4f}")
    print(f"Slowest progressor: {progression_df['progression_rate'].min():.4f}")

    return progression_df


def validate_trajectory_clinical(metadata, pseudotime_column='pseudotime',
                                  clinical_score_column='clinical_score',
                                  stage_column='clinical_stage',
                                  time_column='time_to_event',
                                  event_column='event_occurred',
                                  output_dir='.'):
    """
    Comprehensive clinical validation of disease trajectory.

    Performs multiple validation analyses:
    - Correlation with clinical scores
    - Comparison across clinical stages
    - Survival analysis
    - Progression rate calculation

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata with all required columns
    pseudotime_column : str
        Column name for pseudotime values
    clinical_score_column : str, optional
        Column name for clinical severity score
    stage_column : str, optional
        Column name for clinical stage categories
    time_column : str, optional
        Column name for time to event
    event_column : str, optional
        Column name for event occurrence
    output_dir : str
        Directory to save output plots

    Returns
    -------
    dict
        All validation results
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    results = {}

    # 1. Correlation with clinical scores
    if clinical_score_column in metadata.columns:
        print("\n" + "=" * 60)
        print("1. CORRELATION WITH CLINICAL SCORES")
        print("=" * 60)
        corr_results = correlate_with_clinical_scores(
            metadata, pseudotime_column,
            clinical_columns=[clinical_score_column]
        )
        results['clinical_correlation'] = corr_results

    # 2. Comparison across stages
    if stage_column in metadata.columns:
        print("\n" + "=" * 60)
        print("2. COMPARISON ACROSS CLINICAL STAGES")
        print("=" * 60)
        stage_results = compare_by_clinical_stage(
            metadata, pseudotime_column, stage_column,
            output_file=os.path.join(output_dir, 'pseudotime_by_stage.svg')
        )
        results['stage_comparison'] = stage_results

    # 3. Survival analysis
    if time_column in metadata.columns and event_column in metadata.columns:
        print("\n" + "=" * 60)
        print("3. SURVIVAL ANALYSIS")
        print("=" * 60)
        survival_results = survival_analysis(
            metadata, pseudotime_column, time_column, event_column,
            output_file=os.path.join(output_dir, 'survival_curves.svg')
        )
        results['survival'] = survival_results

    # 4. Progression rates
    if 'timepoint' in metadata.columns and 'patient_id' in metadata.columns:
        print("\n" + "=" * 60)
        print("4. PROGRESSION RATE CALCULATION")
        print("=" * 60)
        progression_results = compute_progression_rate(
            metadata, pseudotime_column
        )
        results['progression_rates'] = progression_results

        # Save progression rates
        progression_results.to_csv(
            os.path.join(output_dir, 'patient_progression_rates.csv'),
            index=False
        )

    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE")
    print("=" * 60)

    return results

