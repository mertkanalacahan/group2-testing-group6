"""Command-line entry point for the Team 6 issue analyses."""
import argparse
import config


def main():
    parser = argparse.ArgumentParser(description='Team 6 issue analysis')
    parser.add_argument('--feature', '-f', type=int, required=True,
                        help='0: template example; 1: time to closure; 2: contributor profile; 3: time to first response')
    parser.add_argument('--user', '-u', help='GitHub username for feature 2')
    parser.add_argument('--label', '-l')
    parser.add_argument('--output-dir', default=None,
                        help='Folder for saved charts and tables (each feature has its own default)')
    parser.add_argument('--show', action='store_true', help='Also open interactive charts')
    args = parser.parse_args()
    config.overwrite_from_args(args)
    if args.feature == 0:
        from example_analysis import ExampleAnalysis
        ExampleAnalysis().run()
    elif args.feature == 1:
        from resolution_time_analysis import ResolutionTimeAnalysis
        try:
            ResolutionTimeAnalysis().run()
        except (OSError, ValueError, TypeError, KeyError) as error:
            parser.exit(1, f'Unable to run analysis: {error}\nCheck the dataset path and JSON format.\n')
    elif args.feature == 2:
        from contributor_profile_analysis import ContributorProfileAnalysis
        try:
            ContributorProfileAnalysis().run()
        except (OSError, ValueError, TypeError, KeyError) as error:
            parser.exit(1, f'Unable to run analysis: {error}\nCheck the dataset path and JSON format.\n')
    elif args.feature == 3:
        from response_time_analysis import ResponseTimeAnalysis
        try:
            ResponseTimeAnalysis().run()
        except (OSError, ValueError, TypeError, KeyError) as error:
            parser.exit(1, f'Unable to run analysis: {error}\nCheck the dataset path and JSON format.\n')
    else:
        parser.error('Available features: 0 (template example), 1 (time to closure), '
                     '2 (contributor profile), 3 (time to first response).')


if __name__ == '__main__':
    main()
